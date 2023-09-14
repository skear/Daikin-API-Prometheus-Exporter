import requests
import os
import sys
import time
from datetime import datetime, timedelta
import logging
from flask import Flask, Response
from threading import Thread

app = Flask(__name__)
web_port = 8000

# Configure logging to print to the console at the INFO level
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Load API keys
api_key = os.environ.get('DAIKIN_API_KEY')
integrator_token = os.environ.get('DAIKIN_API_TOKEN')
email = os.environ.get('DAIKIN_API_EMAIL')

if api_key is None or integrator_token is None or email is None:
    logging.info("Environment variables (DAIKIN_API_KEY, DAIKIN_API_TOKEN, DAIKIN_API_EMAIL) are not set.")
    sys.exit(1)

'''
API USAGE LIMITS
Please wait a minimum of 15 seconds for successful changes to be reflected
Do Not poll at an interval quicker than once every 3 minutes
Do Not have more than 3 open HTTP requests at any given time
'''

class ThermostatMetrics:
    def __init__(self, token_manager, thermostat_name):
        self.token_manager = token_manager
        self.thermostat_name = thermostat_name
        self.prom_data = None

    def update_metrics(self):
        logging.info(f"Updating thermostat information for {self.thermostat_name}")
        thermostat_info = get_thermostat_information(self.thermostat_name, self.token_manager)
        self.prom_data = create_prometheus_report(self.thermostat_name, thermostat_info)

    def get_metrics(self):
        return self.prom_data

class TokenManager:
    def __init__(self, api_key, email, integrator_token):
        self.api_key = api_key
        self.home_app_email = email
        self.integrator_token = integrator_token
        self.access_token = None
        self.expiry_time = None

    def get_token(self):
        if self.access_token and datetime.now() < self.expiry_time:
            return self.access_token

        self.access_token = get_access_token(self.api_key, self.home_app_email, self.integrator_token)
        expires_in = 900  # You can extract this from the response if it varies
        self.expiry_time = time.time() + expires_in - 60  # Subtracting 60 seconds to provide a buffer

        return self.access_token

    def get_valid_token(self):
        if self.access_token is None or datetime.now() >= self.expiry_time:
            logging.info("Requesting a new access token")
            self.access_token, self.expiry_time = self.get_token()
        return self.access_token


def get_access_token(api_key, homeAppEmail, integratorToken):

    url = "https://integrator-api.daikinskyport.com/v1/token"

    headers = {
        "x-api-key": api_key,
        "Content-Type": "application/json"
    }

    data = {
        "email": homeAppEmail,
        "integratorToken": integratorToken
    }

    response = requests.post(url, json=data, headers=headers)

    if response.status_code == 200:
        logging.info("Successfully retrieved a new access token")
        token_data = response.json()
        expiry_time_seconds = token_data["accessTokenExpiresIn"]
        expiry_time = datetime.now() + timedelta(seconds=expiry_time_seconds)
        return token_data["accessToken"], expiry_time
    if response.status_code == 400:
        logging.info("Error 400 (bad request), check API credentials.")
        logging.info("Sleeping for 60 seconds")
        time.sleep(60)
    if response.status_code == 429:
        logging.info("Too Many Requests - Rate of API calls is too high")
        logging.info("Sleeping for 300 seconds")
        time.sleep(300)
    else:
        response.raise_for_status()


def get_thermostats(accessToken, api_key):
    url = "https://integrator-api.daikinskyport.com/v1/devices/"

    headers = {
        "Authorization": f"Bearer {accessToken}",
        "x-api-key": api_key
    }

    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        return response.json()
    else:
        response.raise_for_status()

def get_thermostat_id_by_name(thermostat_name, access_token, api_key):
    headers = {
        'Authorization': f'Bearer {access_token}',
        'x-api-key': api_key,
    }
    url = "https://integrator-api.daikinskyport.com/v1/devices/"
    response = requests.get(url, headers=headers)
    for location in response.json():
        for device in location['devices']:
            if device['name'].lower() == thermostat_name.lower():
                return device['id']
    return None

def get_thermostat_information(thermostat_name, token_manager):
    access_token = token_manager.get_valid_token()
    thermostat_id = get_thermostat_id_by_name(thermostat_name, access_token, token_manager.api_key)
    if thermostat_id is None:
        raise Exception(f"No thermostat found with name: {thermostat_name}")

    headers = {
        'Authorization': f'Bearer {access_token}',
        'x-api-key': token_manager.api_key,
    }
    logging.info(f"Updating data from {thermostat_name}")
    url = f"https://integrator-api.daikinskyport.com/v1/devices/{thermostat_id}"
    response = requests.get(url, headers=headers)
    return response.json()


def create_prometheus_report(thermostat_name, thermostat_info):

    thermostat_info['modeEmHeatAvailable'] = 1 if thermostat_info['modeEmHeatAvailable'] else 0
    thermostat_info['scheduleEnabled'] = 1 if thermostat_info['scheduleEnabled'] else 0
    thermostat_info['geofencingEnabled'] = 1 if thermostat_info['geofencingEnabled'] else 0

    prom_data = f"""
# HELP home_thermostat_setpointMinimum Minimum temperature threshold supported by the system in 0.1 degree Celsius
home_thermostat_setpointMinimum{{thermostat_name="{thermostat_name}"}} {thermostat_info['setpointMinimum']}
# HELP home_thermostat_fan System fan (0: auto 1: on)
home_thermostat_fan{{thermostat_name="{thermostat_name}"}} {thermostat_info['fan']}
# HELP home_thermostat_humIndoor Current indoor humidity percentage
home_thermostat_humIndoor{{thermostat_name="{thermostat_name}"}} {thermostat_info['humIndoor']}
# HELP home_thermostat_modeLimit Thermostat mode limits (0: none 1: all 2: heat only 3: cool only)
home_thermostat_modeLimit{{thermostat_name="{thermostat_name}"}} {thermostat_info['modeLimit']}
# HELP home_thermostat_tempOutdoor Current outdoor temperature. 0.1 degrees Celsius increments
home_thermostat_tempOutdoor{{thermostat_name="{thermostat_name}"}} {thermostat_info['tempOutdoor']}
# HELP home_thermostat_mode Thermostat mode (0: off 1: heat 2: cool 3: auto 4: emergency heat)
home_thermostat_mode{{thermostat_name="{thermostat_name}"}} {thermostat_info['mode']}
# HELP home_thermostat_setpointMaximum Maximum temperature threshold supported by the system in 0.1 degree Celsius
home_thermostat_setpointMaximum{{thermostat_name="{thermostat_name}"}} {thermostat_info['setpointMaximum']}
# HELP home_thermostat_coolSetpoint Cooling threshold for the "Manual" operating mode in 0.1 degree Celsius
home_thermostat_coolSetpoint{{thermostat_name="{thermostat_name}"}} {thermostat_info['coolSetpoint']}
# HELP home_thermostat_heatSetpoint Heating threshold for the "Manual" operating mode in 0.1 degree Celsius
home_thermostat_heatSetpoint{{thermostat_name="{thermostat_name}"}} {thermostat_info['heatSetpoint']}
# HELP home_thermostat_fanCirculateSpeed Speed at which fan should run when circulating on a schedule (0: low 1: medium 2: high)
home_thermostat_fanCirculateSpeed{{thermostat_name="{thermostat_name}"}} {thermostat_info['fanCirculateSpeed']}
# HELP home_thermostat_equipmentStatus HVAC equipment status (1: cool 2: overcool for dehum 3: heat 4: fan 5: idle)
home_thermostat_equipmentStatus{{thermostat_name="{thermostat_name}"}} {thermostat_info['equipmentStatus']}
# HELP home_thermostat_humOutdoor Current outdoor humidity in percentage
home_thermostat_humOutdoor{{thermostat_name="{thermostat_name}"}} {thermostat_info['humOutdoor']}
# HELP home_thermostat_tempIndoor Current indoor temperature. 0.1 degrees Celsius increments
home_thermostat_tempIndoor{{thermostat_name="{thermostat_name}"}} {thermostat_info['tempIndoor']}
# HELP home_thermostat_setpointDelta Minimum temperature delta in 0.1 degree Celsius increments
home_thermostat_setpointDelta{{thermostat_name="{thermostat_name}"}} {thermostat_info['setpointDelta']}
# HELP home_thermostat_equipmentCommunication 
home_thermostat_equipmentCommunication{{thermostat_name="{thermostat_name}"}} {thermostat_info['equipmentCommunication']}
# HELP home_thermostat_fanCirculate Run the fan on a schedule (0: off 1: always on 2: on a schedule)
home_thermostat_fanCirculate{{thermostat_name="{thermostat_name}"}} {thermostat_info['fanCirculate']}
# HELP home_thermostat_modeEmHeatAvailable Emergency heat is available as a system mode (0: not available 1: available)
home_thermostat_modeEmHeatAvailable{{thermostat_name="{thermostat_name}"}} {thermostat_info['modeEmHeatAvailable']}
# HELP home_thermostat_geofencingEnabled Status of the geofencing feature
home_thermostat_geofencingEnabled{{thermostat_name="{thermostat_name}"}} {thermostat_info['geofencingEnabled']}
# HELP home_thermostat_scheduleEnabled Enable schedule operation
home_thermostat_scheduleEnabled{{thermostat_name="{thermostat_name}"}} {thermostat_info['scheduleEnabled']}
"""

    return prom_data


def data_collection_loop():
    while True:
        try:
            thermostat_metrics.update_metrics()
            time.sleep(180)  # Wait 3 minutes between API polls
        except Exception as e:
            logging.error(f"An error occurred while updating metrics: {e}")

token_manager = TokenManager(api_key, email, integrator_token)
thermostat_name = "Downstairs"
thermostat_metrics = ThermostatMetrics(token_manager, thermostat_name)

# Start the data collection loop in a separate thread
logging.info("Starting data collection thread")
data_collection_thread = Thread(target=data_collection_loop)
data_collection_thread.daemon = True  # This allows the thread to exit when the main program exits
data_collection_thread.start()

@app.route("/metrics")
def metrics():
    prom_data = thermostat_metrics.get_metrics()
    return Response(prom_data, content_type='text/plain')

app.run(host='0.0.0.0', port=web_port)




