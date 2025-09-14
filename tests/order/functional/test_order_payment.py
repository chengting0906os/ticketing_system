from pytest_bdd import scenarios
from pathlib import Path

# Load scenarios from the BDD feature file
scenarios(Path(__file__).parent.parent.parent / 'features' / 'order_payment.feature')
