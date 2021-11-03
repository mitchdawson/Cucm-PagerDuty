from headers import get_line_headers, update_line_headers
from requests import Session
from xml_messages import get_line_cfwdall_dest_xml, \
    update_line_cfwdall_dest_xml


class Cucm(Session):

    def __init__(self, **kwargs):

        # Initialise the "Session" super class
        super().__init__()
        # Iterate through the kwargs
        for k, v in kwargs.items():
            setattr(self, k, str(v))
        self.auth = (self.axl_user, self.axl_pass)

    def make_request(self, headers, message):
        self.headers = headers
        return self.post(
            url=self.cucm_axl_url, headers=headers,
            data=message
        )

    def get_line_cfwdall_value(self, pattern, partition):
        # Format our XML Message
        msg = get_line_cfwdall_dest_xml.format(
            self.cucm_ver, pattern, partition
        )
        # Make the request
        return self.make_request(get_line_headers(self.cucm_ver), msg)

    def set_line_cfwdall_value(self, pattern, partition, cfwdall_value):
        # Format our XML Message
        msg = update_line_cfwdall_dest_xml.format(
            self.cucm_ver, pattern, partition, cfwdall_value
        )
        # Make the request
        return self.make_request(update_line_headers(self.cucm_ver), msg)
