# Daikin-API-Prometheus-Exporter
Prometheus exporter to collect data from Daiken Open API for smart thermostats.

https://www.daikinone.com/openapi/index.html
https://www.daikinone.com/openapi/documentation/index.html (Data definitions can be found here)

Requires Flask (pip install flask)

# Obtaining API key and integration token
1. Download the Daikin One Home App or Amana Home App and create an account. Follow app instructions to add thermostats.
2. Request the Integrator Token by navigating to “cloud services” -> “home integration” -> “get integration token”.
3. Enable the developer menu.
iOS: Go to the Settings app -> Navigate to the Daikin One Home or Amana Home App and switch on the developer menu option.
Android: Within the Home App, navigate to "cloud services" -> "home integration" and click on the page description 5 times to enable the developer menu

Once enabled, you will be able to navigate to "cloud services" -> "home integration" -> "developer". Upon entering the developer option.
Enter the name of the application being integrated with the Daikin One Open API and submit the request. 

# Usage
Configure the following environmental variables on your system.

DAIKIN_API_KEY <enter your API key>
DAIKIN_API_TOKEN <enter API token>
DAIKIN_API_EMAIL <enter email address used to log into Daikin app>

If you want to change the web server port the exporter uses you can modify the web_port variable in the script.

python daikin_prom_exporter.py

