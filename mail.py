from smtplib import SMTP
from email.utils import formataddr
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.message import Message


class Mail():

    def __init__(self, smtp_host, smtp_port):

    @staticmethod
    def build_message(sender, destination, subject, body):
        # Set the From value
        msg = MIMEText(body)
        msg['From'] = formataddr(('Author', sender))
        msg['To'] = formataddr(('Recipient', destination))
        msg['Subject'] = subject
        # msg.attach(MIMEText(body, 'plain'))
        return msg

    def send_generic_mail(self):
        sender = "PagerDutyCallFwd@BigCorp.com"
        destination = 'mitch.dawson@BigCorp.com'
        subject = "PagerDuty On Call Forward Application Notification"
        body = "We have successfully changed the call forward all value for the destination"
        msg = self.build_message(sender, destination, subject, body)
        print(msg.as_string())
        self.set_debuglevel(True)
        self.sendmail(sender, [destination], msg.as_string())
        self.quit()
