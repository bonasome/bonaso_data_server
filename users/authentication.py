from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.exceptions import AuthenticationFailed

class CookieJWTAuthentication(JWTAuthentication):
    '''
    Get an access token
    '''
    def authenticate(self, request):
        access_token = request.COOKIES.get('access_token')
        if not access_token:
            return None 
        try:
            validated_token = self.get_validated_token(access_token)
            user = self.get_user(validated_token)
        except Exception as e:
            raise AuthenticationFailed(f'Authentication failed: {str(e)}')

        return (user, validated_token)