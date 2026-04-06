# ehr_pipeline/app/core/exceptions.py

class RCMException(Exception):
    pass


class ValidationException(RCMException):
    pass


class SubmissionException(RCMException):
    pass


class DenialException(RCMException):
    pass