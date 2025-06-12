from rest_framework import serializers
from respondents.models import Respondent

class RespondentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Respondent
        fields = ['id', 'uuid', 'is_anonymous', 'first_name', 'last_name', 'sex', 'village', 'district', 'comments']