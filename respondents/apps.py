from django.apps import AppConfig


class RespondentsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'respondents'

    def ready(self):
        import respondents.signals

'''
signals are used to 
    1) Trigger certain respondent attributes automatically for easier verification (i.e., HIV Status)
    2) Trigger certain respondent statuses when certain interactions occur 
       (i.e., Interaction for tested positive for HIV --> mark as HIV Positive)
    3) Send alerts for interaction flags
'''
