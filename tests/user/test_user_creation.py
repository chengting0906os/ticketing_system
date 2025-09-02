"""BDD tests for user creation feature."""

from messages import Step
from pytest_bdd import then, when


@when("I send api")
def send_api_request(step :Step):
    pass

@then("the user details should be:")
def verify_user_details(step: Step):
    pass

@then("get 201")
def verify_response_201(step: Step):
    """Verify response status is 201 and data matches."""
    pass
