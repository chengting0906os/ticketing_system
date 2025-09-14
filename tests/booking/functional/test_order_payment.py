from pathlib import Path

from pytest_bdd import scenarios


# Load scenarios from the BDD feature file
scenarios(Path(__file__).parent.parent.parent / 'features' / 'booking_payment.feature')
