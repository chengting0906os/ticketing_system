from typing import Any

from pytest_bdd import then


@then('the login response should be successful')
def verify_login_success(context: dict[str, Any]) -> None:
    response = context['response']
    assert response.status_code == 200, (
        f'Expected success status code (200), got {response.status_code}'
    )


@then('the login response should fail')
def verify_login_failure(context: dict[str, Any]) -> None:
    response = context['response']
    assert response.status_code >= 400, (
        f'Expected failure status code (>=400), got {response.status_code}'
    )


@then('the response should contain a JWT cookie')
def verify_jwt_cookie(context: dict[str, Any]) -> None:
    response = context['response']
    cookies = response.cookies
    assert len(cookies) > 0, 'No cookies found in response'
    auth_cookie = cookies.get('fastapiusersauth')
    assert auth_cookie is not None, 'JWT authentication cookie not found'
    assert len(auth_cookie) > 0, 'JWT cookie is empty'
