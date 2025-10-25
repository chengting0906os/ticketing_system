"""Given steps for seat reservation SSE test"""

from pytest_bdd import given


@given('user is connected to SSE stream for event 1')
def user_connected_to_sse(context):
    context['sse_connected'] = True
    context['sse_events'] = []
    context['event_id'] = 1
