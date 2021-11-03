from smtplib import SMTP
import sys
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
import re
import xmltodict
from cucm import Cucm
import os
from json import loads, dumps
import requests
import logging
from custom_exceptions import OnCallDataNotReturned, \
    Escalation1NotFound, ContactMethodNotFound, MobileContactDataNotReturned, \
    CucmDataNotFound, CucmCallFwdAllRetrieveError, CucmSetCallFwdAllError
from logging.handlers import RotatingFileHandler
from requests import Session
from requests.packages.urllib3.exceptions import InsecureRequestWarning
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)


class PagerDuty(Session):

    def __init__(
        self, schedule_id, data,
        cucm_data, time_zone, smtp_host, smtp_port,
        smtp_sender, object_limit=100, verify=False
    ):
        # Initialise the "Session" super class
        super().__init__()
        # Define the Schedule ID
        self.schedule_id = schedule_id
        # Define the input data
        self.data = data
        # Define the PagerDuty API host Url
        self.pd_api_host = self.data[self.schedule_id]["pd_api_host"]
        # Set the headers on the Session
        self.headers = self.data[self.schedule_id]["pd_api_headers"]
        # Define the cucm input data
        self.cucm_data = cucm_data
        # Define the pagerduty timezone used for scheduling
        self.time_zone = time_zone
        # Define the smtp relay host for email
        self.smtp_host = smtp_host
        # Define the smtp relay port for email
        self.smtp_port = smtp_port
        # Define the smtp sender address
        self.smtp_sender = smtp_sender
        # Set the returned Object Limit
        self.object_limit = object_limit
        # Turn off https certificate verification
        self.verify = verify
        # Create Our Logger Instance
        self.logger = logging.getLogger('on_call_forward')
        # Set a flag for the result status
        self.success = False

    def make_get_request(self, api_endpoint_url):
        # Make get requests against the api for the given url
        # Returns Python Dict objects if successful
        return requests.get(
            api_endpoint_url, verify=False,
            headers=self.headers
        )

    def get_on_call_request(self):
        # Build the Parameters for url encoding
        params = {
            "time_zone": self.time_zone,
            "limit": self.object_limit,
            "schedule_ids[]": [self.schedule_id]
        }
        # Build the Full Url
        return requests.get(
            self.pd_api_host + '/oncalls?', params=params,
            verify=False, headers=self.headers
        )

    def get_user(self, schedule_1):
        # Get the User Object of the user in the schedule
        self.logger.info('The following user "{}" is on call. Attempting to retrieve the on call user object at "{}"'.format(
            schedule_1['user']['summary'], schedule_1['user']['self']))
        user = self.make_get_request(schedule_1['user']['self'])
        # Check we have a valid response
        if user.status_code != 200:
            self.logger.info(
                'A status code of "{}" was returned indicating a problem. We will now exit.'.format(user.status_code))
            return
        self.logger.info('Retrieved the on call user object')
        self.logger.info(user.text)
        return loads(user.text)

    def get_pd_mobile(self, user):
        # Set an idicator of whether the object was found
        contact_url = None
        # Extract the Mobile contact data url
        for c in user['user']['contact_methods']:
            if c['summary'] == self.data[self.schedule_id]['contact_method']:
                contact_url = c['self']
        # Check we have found the requested contact method
        if not contact_url:
            raise ContactMethodNotFound(
                'A contact method of "{}" was not found in the pagerduty user object'.format(
                    self.data[self.schedule_id]['contact_method'])
            )
        self.logger.info(
            'Attempting to retrieve the "Mobile" contact method for user "{}"'.format(
                user['user']['name'])
        )
        # Get the contact Methods for the user
        pd_mobile = self.make_get_request(contact_url)
        # Check we have a valid response
        if pd_mobile is None \
                or pd_mobile.status_code != 200:
            self.logger.info(
                'The value of pd_mobile is None or the status code returned indicates a problem with the request. We will now exit.'
            )
            self.logger.info(pd_mobile.text)
            raise MobileContactDataNotReturned(
                'The request to retrieve the Mobile contact data failed'
            )
        self.logger.info(pd_mobile.text)
        return pd_mobile

    def extract_on_call_data(self, on_call_data):
        # print(on_call_data)
        # print(type(on_call_data))
        # Check if we have a list of a single object
        if isinstance(on_call_data['oncalls'], list):
            for o in on_call_data['oncalls']:
                # print(o)
                # We want escalation level 1, i.e. the first level
                if o['escalation_level'] == 1:
                    return o
        elif on_call_data['oncalls']['escalation_level'] == 1:
            return on_call_data['oncalls']
        else:
            return None

    def get_cucm_data(self, pd_mobile):
        # Check if the country code in the contact method matches
        # a value for our cucm clusers
        self.logger.info(
            'Attempting to retrieve the Cucm cluster data for the user'
        )
        if str(pd_mobile['country_code']) in self.cucm_data.keys():
            return self.cucm_data[str(pd_mobile['country_code'])]

        raise CucmDataNotFound('No cucm data found for country code value "{}"'.format(
            pd_mobile['country_code']))

    def get_cucm_connection(self, cucm_data):
        # Create an instance of our cucm class
        setattr(self, 'cucm', Cucm(**cucm_data))

    def format_on_call_number_values(self, number_data, number):
        # Do we have an e164 number match for the region
        number = re.match(number_data['regex'], number)
        if number:
            return number.group(1)
        self.logger.info(
            'The number "{}" did not match the Regex "{}"'.format(
                number, number_data['regex']
            )
        )
        return None

    def compare_on_call_numbers(self, number_data, pd_no, cucm_no):
        # Format the CUCM call forward all value
        cucm_no = self.format_on_call_number_values(number_data, cucm_no)
        # Format the PagerDuty User Mobile Value
        pd_no = self.format_on_call_number_values(number_data, pd_no)
        # Compare the two Values
        if cucm_no == pd_no:
            return True
        self.logger.info(
            'The cucm call forward all value "{}" did not match the PagerDuty Mobile value "{}"'.format(
                cucm_no, pd_no
            )
        )
        return False

    def build_e164_number(self, pd_no_cc, pd_no_address):
        self.logger.info(
            'Building an e164 representation of the users on call number'
        )
        return '+{}{}'.format(pd_no_cc, pd_no_address)

    def set_cfwd_all_number(self, number_data, e164_number):
        self.logger.info(
            'Attemping to set call forward all value "{}"'.format(
                e164_number
            )
        )
        # Check if the number starts with '+' and prepend '\\'
        if str(number_data['on_call_number']).startswith('+'):
            on_call_no = '\\' + number_data['on_call_number']
        else:
            on_call_no = number_data['on_call_number']
        # Make the cucm api call to set the Value
        return self.cucm.set_line_cfwdall_value(
            on_call_no,
            number_data['on_call_partition'],
            e164_number
        )

    def get_on_call_data(self):
        # Get the current on call data from PagerDuty
        self.logger.info('Attempting to retrieve pager duty on call schedules')
        on_call_data = self.get_on_call_request()
        # Check we have a valid response
        if on_call_data.status_code != 200:
            self.logger.info(
                'A status code of "{}" was returned indicating a problem. We will now exit.'.format(on_call_data.status_code))
            raise OnCallDataNotReturned(
                'No on call data was returned from pager duty')
        self.logger.info('Pager duty on call schedules retrieved successfully')
        self.logger.info(on_call_data.text)
        return loads(on_call_data.text)

    def get_schedule_1(self, on_call_data):
        self.logger.info('Looking for Schedule 1 in received on call data')
        # Extract the Schedule 1 data set
        escalation_1 = self.extract_on_call_data(on_call_data)
        # print('got sched 1')
        if not escalation_1:
            self.logger.error('Schedule 1 not found in received on call data')
            raise Escalation1NotFound(
                'The on call schedule data did not contain "Escalation_level" = 1')
        self.logger.info('Schedule 1 found in received on call data')
        self.logger.info(escalation_1)
        # Returns a python dict
        return escalation_1

    def get_team_on_call_number(self, pd_mobile_cc):
        return self.data[self.schedule_id]['numbers']['country_code'][str(
            pd_mobile_cc)]

    def get_mobile_contact_values(self, pd_mobile):
        pd_mob_data = pd_mobile['contact_method']
        pd_mob_addr = pd_mob_data['address']
        pd_mob_cc = pd_mob_data['country_code']
        self.logger.info(
            'The pd user mobile country code and contact number values are "{}" and "{}"'.format(
                pd_mob_cc, pd_mob_addr
            )
        )
        return pd_mob_data, pd_mob_addr, pd_mob_cc

    def get_cucm_cfwd_all_val(self, number_data):
        # Check if the number starts with '+' and prepend '\\'
        if str(number_data['on_call_number']).startswith('+'):
            on_call_no = '\\' + number_data['on_call_number']
        else:
            on_call_no = number_data['on_call_number']
        # Make the request to get the call forward all value
        cfwd_all_no = self.cucm.get_line_cfwdall_value(
            on_call_no,
            number_data['on_call_partition']
        )
        if cfwd_all_no.status_code != 200:
            self.logger.error(
                'Cucm returned a status code of "{}" which indicates problem with the request. We will now exit.'.format(
                    cfwd_all_no.status_code)
            )
            self.logger.error(cfwd_all_no.text)
            raise CucmCallFwdAllRetrieveError(
                'There was an error retrieving the call forward all value from cucm'
            )
        return cfwd_all_no

    def format_get_cfwd_all_response(self, cfwd_all_no):
        return (
            loads(dumps(xmltodict.parse(cfwd_all_no.text)))
            ['soapenv:Envelope']['soapenv:Body']['ns:getLineResponse']
            ['return']['line']['callForwardAll']['destination']
        )

    def build_and_set_new_cfwd_all_value(self, number_data, pd_mob_cc, pd_mob_addr):
        self.logger.info(
            'There is no existing call forward all destination set.'
        )

        # Build a valid e164 Number
        self.logger.info(
            'Building an e164 representation of the users on call number'
        )
        cfw_e164_number = self.build_e164_number(
            pd_mob_cc, pd_mob_addr
        )
        # Make the cucm api call to set the Value
        self.logger.info(
            'Setting "{}" as the call forward all destination'.format(
                cfw_e164_number
            )
        )
        return self.set_cfwd_all_number(
            number_data,
            cfw_e164_number
        )

    def build_email_message(self, recipients, subject, message):
        msg = MIMEMultipart()
        msg['From'] = 'PagerDutyCfwdAll@bigCorp.com'
        msg['To'] = ", ".join(recipients)
        msg['Subject'] = subject
        msg.attach(MIMEText(message))
        return msg

    def send_email_message(self, sender, recipients, msg):
        s = SMTP(self.smtp_host, self.smtp_port)
        s.sendmail(sender, recipients, msg.as_string())
        s.quit()

    def exception_cleanup(self, exception):
        # Method to cleanup after an exception
        # and to provide email notification of the problem
        # Define the Recipients to Receive the Exception alert
        self.logger.info('Generating email notification of exception')
        # print('recipients == ', self.data[self.schedule_id]['mail_rcpt'])
        # Define the subject for the Exception
        subject = 'PagerDuty Call Forward All Process - ERROR - Caught Exception'
        # Generate the body for the email
        message = """
        Whilst processsing Pager Duty schedule "{}" we encountered the following exception.

        ----------------
        "{}"
        ----------------
        """.format(self.data[self.schedule_id]['pd_summary'], exception)

        # Call stop on the logging module so that we can get the logs from the log File
        # self.logger.shutdown()
        # print(message)
        self.logger.info('Building the Message object')
        # Create a msg object
        msg = self.build_email_message(
            self.data[self.schedule_id]['mail_rcpt'], subject, message)
        # print(msg)
        self.logger.info('Attaching the log file to the mail object')
        # Attach the log file to the email
        part = MIMEBase('application', "octet-stream")
        part.set_payload(open("PagerDutyOnCall.log", "rb").read())
        encoders.encode_base64(part)
        part.add_header(
            'Content-Disposition',
            'attachment; filename="PagerDutyOnCall.log"'
        )
        msg.attach(part)
        self.logger.info('Preparing to send the email')
        # Send the completed message
        self.send_email_message(
            msg['From'], self.data[self.schedule_id]['mail_rcpt'], msg
        )
        self.logger.info('Email sent')

    def success_contact_change_email(self, on_call_pilot_no, on_call_user, on_call_user_mob):
        # Method to cleanup after successful change
        self.logger.info(
            'Generating email notification of Successful change of on call contact')

        # Define the subject for the Exception
        subject = 'PagerDuty Call Forward All Process - Success - Contact Number Updated'
        # Generate the body for the email
        message = """
        Whilst processsing Pager Duty schedule "{0}" we found a change in the on call contact.
        The Pilot Number "{1}" Call Foward All Value has been updated to "{2}",
        belonging to the scheduled on call contact "{3}".
        """.format(
            self.data[self.schedule_id]['pd_summary'],
            on_call_pilot_no, on_call_user_mob, on_call_user
        )
        self.logger.info('Building the Message object')
        # Create a msg object
        msg = self.build_email_message(
            self.data[self.schedule_id]['mail_rcpt'], subject, message)
        self.logger.info('Preparing to send the email')
        # Send the completed message
        self.send_email_message(
            msg['From'], self.data[self.schedule_id]['mail_rcpt'], msg
        )
        self.logger.info('Email sent')

    def process_on_call_schedule(self):
        # Get the on call data as a dict
        on_call_data = self.get_on_call_data()

        # Get the schdule 1 data as a python dict
        schedule_1 = self.get_schedule_1(on_call_data)

        # Get the User Object of the user in the schedule as a python Dict object
        user = self.get_user(schedule_1)

        # Get the Mobile contact Method for the user
        pd_mobile = loads(self.get_pd_mobile(user).text)

        # Break out the values from the contact object
        pd_mob_data, pd_mob_addr, pd_mob_cc = self.get_mobile_contact_values(
            pd_mobile
        )
        # Locate the relevent Cucm cluster based on the contact method country code
        # "44" = EU Cluster, "1" = NA Cluster
        cucm_data = self.get_cucm_data(pd_mob_data)

        self.logger.info('Attempting to create a connection to the cucm cluster at "{}"'.format(
            cucm_data['cucm_axl_url'])
        )
        # Create the connection to CUCM, this sets "self.cucm" attrubute
        # on this PagerDuty Class instance.
        self.get_cucm_connection(cucm_data)

        # Break out the relevent team on call number values that we need
        # from the input data
        number_data = self.get_team_on_call_number(pd_mob_cc)

        self.logger.info(
            'Requesting call forward all value for line "{}" and partition "{}"'.format(
                number_data['on_call_number'], number_data['on_call_partition']
            )
        )

        # Get the Call forward all value for the relevent on call number in CUCM
        # Prepene '\\' which is an escaped '\' EG: number is '\+442078184888'
        cfwd_all_no = self.get_cucm_cfwd_all_val(number_data)

        # Convert the xml data into a Python Dict and break out
        # the call forward all value
        cfwd_all_no = self.format_get_cfwd_all_response(cfwd_all_no)
        self.logger.info(
            'The cucm call forward all value is "{}"'.format(cfwd_all_no)
        )

        # If there is no call forward all value set then 'cfwd_all_no'
        # will be None
        if not cfwd_all_no:
            self.logger.info(
                'There is no existing call forward all destination set.'
            )
            # If we dont have an existing value in CUCM then
            # we set the pd user address value as cfwdall
            self.logger.info(
                'Setting call forward all value to on call users E164 mobile value'
            )
            new_cfwd_all = self.build_and_set_new_cfwd_all_value(
                number_data, pd_mob_cc, pd_mob_addr
            )
            # Check the Status Code
            if new_cfwd_all.status_code != 200:
                self.logger.error(
                    'Cucm returned a status code of "{}" which indicates problem with the request. We will now exit.')
                self.logger.error(new_cfwd_all.text)
                raise CucmSetCallFwdAllError(
                    'There was an error setting the call forward call value on cucm'
                )
            else:
                self.logger.info(
                    'Successfully set the call forward all value to cucm'
                )
                self.success_contact_change_email(
                    # The oncall cucm pilot Number
                    number_data['on_call_number'],
                    # The user that is on call obtained from pager duty
                    user['user']['name'],
                    # Build the value forward all number value
                    '+' + str(pd_mob_cc) + str(pd_mob_addr)
                )

        # Compare the current Cucm cfwdall value with the pd user mobile value
        # If they dont match then we have detected a change in the on call user
        # contact methods
        if cfwd_all_no and not self.compare_on_call_numbers(
            number_data, pd_mob_addr, cfwd_all_no
        ):
            self.logger.info(
                'The pd and cucm on call numbers do not match, indicating a change of on call contact'
            )
            # Build a valid e164 Number
            cfw_e164_number = self.build_e164_number(
                pd_mob_cc, pd_mob_addr
            )

            # Make the cucm api call to set the Value
            cfw_all_update = self.set_cfwd_all_number(
                number_data,
                cfw_e164_number
            )
            # Check the Status Code
            if cfw_all_update.status_code != 200:
                self.logger.error(
                    'Cucm returned a status code of "{}" which indicates problem with the request. We will now exit.'
                )
                self.logger.error(cfw_all_update.text)
                raise CucmSetCallFwdAllError(
                    'There was an error setting the call forward call value on cucm'
                )
            else:
                self.logger.info('The oncall Number was successfully Updated')
                # Send the successful email
                self.success_contact_change_email(
                    # The oncall cucm pilot Number
                    number_data['on_call_number'],
                    # The user that is on call obtained from pager duty
                    user['user']['name'],
                    # Build the value forward all number value
                    '+' + str(pd_mob_cc) + str(pd_mob_addr)
                )
        else:
            self.logger.info(
                'The cucm call forward all value matches the on call user mobile contact number')
            self.logger.info('No further action required. Exiting.')

    def run(self):
        # Process the oncall Schedule
        self.process_on_call_schedule()


def file_paths():
    if getattr(sys, 'freeze', False):
        # running as bundle (aka frozen)
        bundle_dir = sys._MEIPASS
    else:
        # running live
        bundle_dir = os.path.dirname(os.path.abspath(__file__))
    return bundle_dir


def main():

    # Obtain the file path
    path = file_paths()
    # Define a function to send
    log_file = 'PagerDutyOnCall.log'
    # Create an instance for our logger
    logger = logging.getLogger('on_call_forward')
    # Set the level to DEBUG
    logger.setLevel(logging.DEBUG)
    # Create the rotating File handler
    fh = RotatingFileHandler(
        os.path.join(path, log_file),
        mode='a', maxBytes=500000, backupCount=10
    )
    # Set the level to DEBUG
    fh.setLevel(logging.DEBUG)
    # create console handler with a higher log level
    ch = logging.StreamHandler()
    ch.setLevel(logging.ERROR)
    # create formatter and add it to the handlers
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(funcName)s - %(levelname)s - %(message)s')
    fh.setFormatter(formatter)
    ch.setFormatter(formatter)
    # add the handlers to the logger
    logger.addHandler(fh)
    logger.addHandler(ch)
    # Define our input variables
    logger.info('Setting the appropriate input and config file paths')
    # Define our input variables
    logger.info('Initialising input variables')
    # Define the path to the Json input file
    data_file_path = os.path.join(path, 'schedule_data.json')
    # Define the path to the Json input file
    cucm_file_path = os.path.join(path, 'cucm.json')
    # Define the Time Zone used for scheduling
    time_zone = 'UTC'
    # Define the smtp relay host
    smtp_host = 'relaysmtp.hds.int'
    # Define the smtp port
    smtp_port = 25
    # Smtp sender email
    smtp_sender = 'PagerDutyCfwdAll@bigCorp.com'
    # Open the input data File
    data = loads(open(data_file_path, 'r').read())
    logger.info('Successfully opened and read "{}"'.format(data_file_path))
    # Open the cucm data input file
    cucm = loads(open(cucm_file_path, 'r').read())
    logger.info('Successfully opened and read "{}"'.format(cucm_file_path))

    # Iterate through the input Data and process each schedule.
    for schedule_id in data.keys():
        logger.info('Processing Schedule "{}"'.format(
            data[schedule_id]['pd_summary']))
        # Create an instance of the PagerDuty Class
        p = PagerDuty(
            schedule_id, data, cucm, time_zone,
            smtp_host, smtp_port, smtp_sender
        )
        logger.info(
            'Successfull instantiated Class "{}" as p'.format(p.__class__.__name__))
        logger.info('Calling "{}".run()'.format(p.__class__.__name__))

        # Attempt to call the run method
        try:
            p.run()
        except OnCallDataNotReturned as e:
            logger.critical('Caught Exception {}'.format(repr(e)))
            # Run the Exception cleanup
            p.exception_cleanup(repr(e))
        except Escalation1NotFound as e:
            logger.critical('Caught Exception {}'.format(repr(e)))
            # Run the Exception cleanup
            p.exception_cleanup(repr(e))
        except ContactMethodNotFound as e:
            logger.critical('Caught Exception {}'.format(repr(e)))
            # Run the Exception cleanup
            p.exception_cleanup(repr(e))
        except MobileContactDataNotReturned as e:
            logger.critical('Caught Exception {}'.format(repr(e)))
            # Run the Exception cleanup
            p.exception_cleanup(repr(e))
        except CucmDataNotFound as e:
            logger.critical('Caught Exception {}'.format(repr(e)))
            # Run the Exception cleanup
            p.exception_cleanup(repr(e))
        except CucmCallFwdAllRetrieveError as e:
            logger.critical('Caught Exception {}'.format(repr(e)))
            # Run the Exception cleanup
            p.exception_cleanup(repr(e))
        except CucmSetCallFwdAllError as e:
            logger.critical('Caught Exception {}'.format(repr(e)))
            # Run the Exception cleanup
            p.exception_cleanup(repr(e))
        except Exception as e:
            logger.critical('Caught Unhandled Exception {}'.format(repr(e)))
            # Run the Exception cleanup
            p.exception_cleanup(repr(e))


if __name__ == "__main__":
    main()
