from dxlclient.callbacks import EventCallback
from dxlclient.client import DxlClient
from dxlclient.client_config import DxlClientConfig
from threading import Condition
import web
import json
import logging
import sqlite3

"""
Define Logging settings
"""
log_formatter = logging.Formatter('%(asctime)s %(name)s - %(levelname)s - %(message)s')
console_handler = logging.StreamHandler()
console_handler.setFormatter(log_formatter)
logger = logging.getLogger()
# Prevent redundant handlers
if len(logger.handlers) == 0:
    logger.addHandler(console_handler)
logger.setLevel(logging.DEBUG)

settings = {
    'sqlite_file': "ip_domain.db",
    'event_topic': "/mcafee/event/atd/file/report",
    'min_sev': 1
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
        conn = sqlite3.connect(settings['sqlite_file'])
        curs = conn.cursor()
        curs.execute("SELECT domain FROM domains")
        rows = curs.fetchall()

        values = []
        for row in rows:
            values.append(row[0])

        return "\n".join(values)


class ip_list:

    def GET(self):
        conn = sqlite3.connect(settings['sqlite_file'])
        curs = conn.cursor()
        curs.execute("SELECT ip FROM ips")
        rows = curs.fetchall()

        values = []
        for row in rows:
            values.append(row[0])

        return "\n".join(values)


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

    conn.close()

    # Create the client
    with DxlClient(config) as client:

        logger.info("Connecting to OpenDXL")
        # Connect to the fabric
        client.connect()

        logger.info("Connected to OpenDXL")
        #
        # Register callback and subscribe
        #

        # Create and add event listener. This EventCallBack is executed whenever an event is placed on the current
        # topic
        class MyEventCallback(EventCallback):
            def on_event(self, event):
                with event_count_condition:
                    conn = sqlite3.connect(settings['sqlite_file'])
                    curs = conn.cursor()
                    logger.info("Received event")
                    # The ATD json can sometimes have non-standard json characters at the end.
                    # Let's clean it up.

                    # End the json at the last curly brace: }
                    payload_end = event.payload.rfind('}')+1
                    # Offset the payload and escape any backslashes to be interpreted as literals not escape/control
                    # characters
                    clean_payload = event.payload[:payload_end].replace('\\', '\\\\')
                    # Print and assign the payload for the received event
                    atd_result = json.loads(clean_payload)
                    logger.debug(atd_result)

                    # Process URLs discovered in ATD analysis
                    try:
                        for remote in atd_result["Summary"]["Urls"]:
                            if int(remote["Severity"]) >= settings['min_sev']:
                                # This domain is relevant
                                current_domain = remote["Url"].split('/')[0]

                                logger.info("Severity is {}".format(int(remote["Severity"])))
                                logger.info("URL {} is a candidate for Blacklisting".format(current_domain))

                                # First, check to see if the current domain exists
                                curs.execute("SELECT domain, seen_count FROM domains WHERE domain =?",
                                             [current_domain])

                                rows = curs.fetchall()
                                if rows:
                                    # The row exists
                                    # Add 1 to the seen count
                                    curs.execute("UPDATE domains set seen_count = seen_count+1 WHERE domain =?",
                                                 [current_domain])
                                    conn.commit()
                                else:
                                    # The row is new
                                    # Add an entry for the domain
                                    curs.execute("INSERT INTO domains VALUES(?, 1)", [current_domain])
                                    conn.commit()

                    except KeyError as ke:
                        logger.info("Summary/URLs does not exist.")
                        logger.info(ke)

                    # Process IPs discovered in ATD analysis
                    try:
                        for remote in atd_result["Summary"]["Ips"]:
                            if int(remote["Severity"]) >= settings['min_sev']:
                                # This domain is relevant
                                current_ip = remote["Ipv4"]
                                logger.info("Severity is {}".format(int(remote["Severity"])))
                                logger.info("IP {} is a candidate for Blacklisting".format(current_ip))

                                # First, check to see if the current IP exists
                                curs.execute("SELECT ip, seen_count FROM ips WHERE ip =?",
                                            [current_ip])

                                rows = curs.fetchall()
                                if rows:
                                    # The row exists
                                    # Add 1 to the seen count
                                    curs.execute("UPDATE ips set seen_count = seen_count+1 WHERE ip =?",
                                                [current_ip])
                                    conn.commit()
                                else:
                                    # The row is new
                                    # Add an entry for the ip
                                    curs.execute("INSERT INTO ips VALUES(?, 1)", [current_ip])
                                    conn.commit()

                    except KeyError as ke:
                        logger.info("Summary/Ips does not exist.")
                        logger.info(ke)

                    # Increment the count
                    event_count[0] += 1
                    # Notify that the count was increment
                    event_count_condition.notify_all()
                    conn.close()

        # Register the callback with the client
        client.add_event_callback(settings['event_topic'], MyEventCallback())

        # Wait until all events have been received
        logger.info("Waiting for events to be received...")

        if __name__ == "__main__":
            # This ensures we don't run the web service twice
            app.run()


"""
END DEF MAIN
"""

"""
RUN
"""

if __name__ == "__main__":
    # Start the process
    main()

