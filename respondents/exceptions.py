from rest_framework.exceptions import APIException

class DuplicateExists(APIException):
    status_code = 409
    default_detail = "Duplicate entry exists."
    default_code = "duplicate"

    def __init__(self, detail=None, existing_id=None):
        if detail is None:
            detail = self.default_detail
        super().__init__({"detail": detail, "existing_id": existing_id})