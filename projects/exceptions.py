from rest_framework.exceptions import APIException

class ConflictError(APIException):
    status_code = 409
    default_detail = 'Conflict: This resource overlaps with an existing one.'
    default_code = 'conflict'