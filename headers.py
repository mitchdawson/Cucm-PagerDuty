
def get_line_headers(version):
    sa = "CUCM:DB ver={} getLine".format(version)
    return {
        "Content-type": "text/xml",
        "SOAPAction": sa
    }


def update_line_headers(version):
    sa = "CUCM:DB ver={} updateLine".format(version)
    return {
        "Content-type": "text/xml",
        "SOAPAction": sa
    }
