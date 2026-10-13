"""Every test of the repository runs on the environment the test sets, never on a .env file.

The service reads services/perception/.env when SMC_ENV_FILE is unset; a
developer's file there could turn the agent's Bedrock model on in the tests.
This runs before any test module imports the service.
"""

import os

os.environ["SMC_ENV_FILE"] = ""
