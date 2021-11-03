from json import loads, dumps
from requests import Session
import requests
from pprint import pprint


# url = 'https://api.pagerduty.com/users?include%5B%5D=contact_methods'
# Define the PagerDuty '/users' api endpoint
pd_host = 'https://api.pagerduty.com'
users_url = '/users?limit=100'
schedules_url = '/schedules?limit=100'
on_calls = '/oncalls?limit=100'

dim_schedule_id = 'dim-sched-id'
osms_schedule_id = "osmc-sched-id"

# Voice Data
voice_schedule_url = 'https://api.pagerduty.com/schedules/voice-sched-id'
voice_escalation_policy = 'https://api.pagerduty.com/escalation_policies/voice-pol'

# Network Data
network_schedule_url = 'https://api.pagerduty.com/schedules/network-sched-id'

# Duty Incident Manager
dim_schedule_url = 'https://api.pagerduty.com/schedules/dim-sched-id'

# Example User Url
user_url = 'https://api.pagerduty.com/users/user-id'

# Define the required headers
headers = {
    "Accept": "application/vnd.pagerduty+json;version=2",
    "Authorization": "Token token=token"
}

# Dictionary of Schedule ID's
sched_ids = {
    "time_zone": "UTC",
    "limit": 100,
    "schedule_ids[]": [
        osms_schedule_id
    ]
}

# Instantiate the HTTP client
s = Session()
# Disable Verification
s.verify = False
# Add the application and authorization headers
s.headers = headers


def get_data(url):
    return loads(s.get(url=url).text)


def get_network_schedule():
    sched = get_data(network_schedule_url)
    pprint(sched)


def get_voice_schedule():
    sched = get_data(voice_schedule_url)
    pprint(sched)


def get_dim_schedule():
    sched = get_data(dim_schedule_url)
    pprint(sched)


def get_voice_escalation_policy():
    esc = get_data(voice_escalation_policy)
    pprint(esc)


def get_on_calls():
    ocs = s.get('https://api.pagerduty.com/oncalls',
                params=sched_ids
                )
    # ocs = requests.get('https://api.pagerduty.com/oncalls',
    #                    params=sched_ids, verify=False, headers=headers)
    # print(ocs.url)
    print(ocs.status_code)
    print(ocs.url)
    pprint(loads(ocs.text))


def get_user_data():
    user = get_data(user_url)
    pprint(user)


get_on_calls()