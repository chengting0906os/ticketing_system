from pytest_bdd import given

from tests.shared.utils import extract_table_data, login_user


@given('I am logged in as:')
def login_user_with_table(step, client):
    login_data = extract_table_data(step)
    return login_user(client, login_data['email'], login_data['password'])
