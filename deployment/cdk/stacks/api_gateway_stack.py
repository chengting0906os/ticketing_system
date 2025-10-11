"""
API Gateway Stack for Ticketing System
Routes requests to ticketing-service and seat-reservation-service
"""

from aws_cdk import Stack, aws_apigateway as apigw
from constructs import Construct


class ApiGatewayStack(Stack):
    """Creates API Gateway with routes to microservices"""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Create REST API
        api = apigw.RestApi(
            self,
            'TicketingApi',
            rest_api_name='Ticketing System API',
            description='Unified API Gateway for Ticketing System microservices',
            deploy_options=apigw.StageOptions(
                stage_name='prod',
                # Disable CloudWatch - we use Prometheus + Grafana + Loki instead
                metrics_enabled=False,
                logging_level=apigw.MethodLoggingLevel.OFF,
                data_trace_enabled=False,
            ),
            # Disable automatic CloudWatch role creation
            cloud_watch_role=False,
        )

        # Create /api resource
        api_resource = api.root.add_resource('api')

        # ============= TICKETING SERVICE ROUTES =============

        # /api/user - User authentication and management
        user_resource = api_resource.add_resource('user')
        self._add_http_proxy(
            user_resource, 'http://ticketing-service:8000/api/user', with_proxy=True
        )

        # /api/event - Event management
        event_resource = api_resource.add_resource('event')
        self._add_http_proxy(
            event_resource, 'http://ticketing-service:8000/api/event', with_proxy=True
        )

        # /api/booking - Booking operations
        booking_resource = api_resource.add_resource('booking')
        self._add_http_proxy(
            booking_resource, 'http://ticketing-service:8000/api/booking', with_proxy=True
        )

        # ============= SEAT RESERVATION SERVICE ROUTES =============

        # /api/reservation - Seat allocation and reservation
        reservation_resource = api_resource.add_resource('reservation')
        self._add_http_proxy(
            reservation_resource,
            'http://seat-reservation-service:8000/api/reservation',
            with_proxy=True,
        )

        # Output API endpoint
        from aws_cdk import CfnOutput

        CfnOutput(
            self,
            'ApiEndpoint',
            value=api.url,
            description='API Gateway endpoint URL',
        )

    def _add_http_proxy(
        self, resource: apigw.Resource, backend_url: str, *, with_proxy: bool = False
    ) -> None:
        """
        Add HTTP proxy integration to a resource

        Args:
            resource: API Gateway resource to add method to
            backend_url: Backend service URL (e.g., http://service:8000/api/event)
            with_proxy: If True, also create {proxy+} sub-resource for nested paths
        """
        # Add ANY method to base resource (e.g., /api/event)
        resource.add_method(
            'ANY',
            apigw.HttpIntegration(
                backend_url,
                http_method='ANY',
                options=apigw.IntegrationOptions(
                    integration_responses=[
                        apigw.IntegrationResponse(
                            status_code='200',
                            response_parameters={
                                'method.response.header.Access-Control-Allow-Origin': "'*'"
                            },
                        )
                    ],
                ),
            ),
            method_responses=[
                apigw.MethodResponse(
                    status_code='200',
                    response_parameters={
                        'method.response.header.Access-Control-Allow-Origin': True
                    },
                )
            ],
        )

        # Add {proxy+} for sub-paths (e.g., /api/event/1, /api/event/1/seats)
        if with_proxy:
            proxy_resource = resource.add_resource('{proxy+}')
            proxy_resource.add_method(
                'ANY',
                apigw.HttpIntegration(
                    f'{backend_url}/{{proxy}}',
                    http_method='ANY',
                    options=apigw.IntegrationOptions(
                        request_parameters={
                            'integration.request.path.proxy': 'method.request.path.proxy'
                        },
                        integration_responses=[
                            apigw.IntegrationResponse(
                                status_code='200',
                                response_parameters={
                                    'method.response.header.Access-Control-Allow-Origin': "'*'"
                                },
                            )
                        ],
                    ),
                ),
                request_parameters={'method.request.path.proxy': True},
                method_responses=[
                    apigw.MethodResponse(
                        status_code='200',
                        response_parameters={
                            'method.response.header.Access-Control-Allow-Origin': True
                        },
                    )
                ],
            )
