"""Given steps for seat reservation SSE test"""

from pytest_bdd import given, parsers


@given(parsers.parse('user is connected to SSE stream for event {event_id}'))
def user_connected_to_sse(context, event_id):
    context['sse_connected'] = True
    context['sse_events'] = []
    context['event_id'] = event_id
