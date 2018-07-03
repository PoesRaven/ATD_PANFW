from dxlclient.callbacks import EventCallback
from dxlclient.client import DxlClient
from dxlclient.client_config import DxlClientConfig
from dxlbootstrap.util import MessageUtils
from dxlclient.message import Event
import time
from threading import Condition
import web
import json
import logging
import sqlite3

log_formatter = logging.Formatter('%(asctime)s %(name)s - %(levelname)s - %(message)s')
console_handler = logging.StreamHandler()
console_handler.setFormatter(log_formatter)
logger = logging.getLogger()
if len(logger.handlers) == 0:
    logger.addHandler(console_handler)
logger.setLevel(logging.DEBUG)
#logging.getLogger().setLevel(logging.ERROR)

settings = {
    'sqlite_file': "ip_domain.db",
    'event_topic': "/mcafee/event/atd/file/report",
}

"""
The following lines define the web services content. This will be used to generate IP address and domains to feed 
third party products like palo alto firewall.
"""
urls = (
    '/domain', 'domain_list',
    '/ip', 'ip_list',
)
app = web.application(urls, globals())

class domain_list:
    def GET(self):
        return "shinolocker.com"
"""
END WEB SERVICES DEF
"""

"""
The following lines define the OpenDXL content. This code is used to setup a listener waiting for ATD results. Once 
caught, the results are written to an SQLite DB

"""
def main():
    # Create DXL configuration from file
    config = DxlClientConfig.create_dxl_config_from_file('dxlclient.config')
    logger.info("Starting the ATD/PAN FW OpenDXL integrator")
    # Create the client


    # Condition/lock used to protect changes to counter
    event_count_condition = Condition()
    event_count = {}
    event_count[0] = 0

    conn = sqlite3.connect(settings['sqlite_file'])
    curs = conn.cursor()

    curs.execute("""
                  CREATE TABLE IF NOT EXISTS domains (domain text,
                                                      seen_count int)
                """)
    curs.execute("""
                  CREATE TABLE IF NOT EXISTS ips (ip text,
                                                  seen_count int)
                """)


    # Create the client
    with DxlClient(config) as client:

        logger.info("Connecting to OpenDXL")
        # Connect to the fabric
        client.connect()

        logger.info("Connected to OpenDXL")
        #
        # Register callback and subscribe
        #

        # Create and add event listener
        class MyEventCallback(EventCallback):
            def on_event(self, event):
                with event_count_condition:
                    # Print the payload for the received event
                    logger.info("Received event")
                    # The last 3 digits are fubar
                    logger.debug(event.payload.decode()[:-3])
                    atd_result = json.loads(event.payload.decode()[:-3])
                    print atd_result

                    for remote in atd_result["Summary"]["Urls"]:
                        if remote["Severity"] >= 3:
                            # This domain is relevant
                            current_domain = remote["Url"]

                            # First, check to see if the current domain exists
                            curs.execute("SELECT domain, seen_count FROM domains WHERE domain =?",
                                         (current_domain, ))

                            rows = cur.fetchall()

                            if rows:
                                # Add 1 to the seen count
                                curs.execute("UPDATE domain set seen_count = seen_count+1 WHERE domain =?",
                                             (current_domain, ))
                                conn.commit()
                            else:
                                # Add an entry for the domain
                                curs.execute("INSERT INTO domain VALUES(?, 1)", current_domain)
                                conn.commit()


                    # Increment the count
                    event_count[0] += 1
                    # Notify that the count was increment
                    event_count_condition.notify_all()
                    # Write the domain to the local sqlite db


        # Register the callback with the client
        client.add_event_callback(settings['event_topic'], MyEventCallback())


        # Wait until all events have been received
        logger.info("Waiting for events to be received...")

        if __name__ == "__main__":
            app.run()

if __name__ == "__main__":
    main()
"""
with event_count_condition:
    while True:
        event_count_condition.wait()
"""

