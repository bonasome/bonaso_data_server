from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views import View
from django.forms.models import model_to_dict
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework.exceptions import PermissionDenied
from rest_framework import generics

import json
from datetime import datetime
from respondents.models import Respondent, KeyPopulationStatus, Pregnancy, HIVStatus, Interaction
from respondents.serializers import RespondentSerializer

class GetModelInfo(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):
        sex_values = []
        sex_labels = []
        for value, label in Respondent.sex.field.choices:
            sex_values.append(value)
            sex_labels.append(label)

        age_values = []
        age_labels = []
        for value, label in Respondent.age_range.field.choices:
            age_values.append(value)
            age_labels.append(label)

        kp_values = []
        kp_labels = []
        for value, label in KeyPopulationStatus.kp_status.field.choices:
            kp_values.append(value)
            kp_labels.append(label)
        
        district_values = []
        district_labels = []
        for value, label in Respondent.district.field.choices:
            district_values.append(value)
            district_labels.append(label)

        data = {
            'values':{
                'sex': sex_values,
                'age_range': age_values,
                'kp': kp_values,
                'district': district_values,
            },  
            'labels': {
                'sex': sex_labels,
                'age_range': age_labels,
                'kp': kp_labels,
                'district': district_values,
            }
        }
        return JsonResponse(data, safe=False)

class ViewRespondent(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request, pk):
        respondent = Respondent.objects.get(pk=pk)
        data = model_to_dict(respondent)
        if not data['age_range']:
            data['age_range'] = respondent.get_age_range()
        return JsonResponse(data, safe=False)

#consider adding more checks on this, but depends on how we handle editing, so come back to it later
class CreateRespondent(APIView):
    permission_classes = [IsAuthenticated]
    def post(self, request):
        user = request.user
        data = json.loads(request.body)
        form = data['formData']
        respondent = None
        isAnonymous = form['isAnonymous']
        if isAnonymous:
            if 'uuid' in form:
                uuid = form['uuid']
                checkRespondent = Respondent.objects.filter(uuid = uuid).first()
                if checkRespondent:
                    respondent = checkRespondent
        else:
           idNo = form['id_no']
           checkRespondent =  Respondent.objects.filter(id_no = idNo).first()
           if checkRespondent:
               respondent = checkRespondent
        if not respondent:
            respondent = Respondent(is_anonymous=isAnonymous)
        respondent.sex = form['sex']
        respondent.village = form['village']
        respondent.district = form['district']
        respondent.citizenship = form['citizenship']
        respondent.comments = form['comments']
        if isAnonymous:
            respondent.age_range = form['age_range']
        if not isAnonymous:
            respondent.id_no = form['id_no']
            respondent.dob = form['dob']
            respondent.first_name = form['first_name']
            respondent.last_name = form['last_name']
            respondent.email = form['email']
            respondent.phone_number = form['phone_number']
            respondent.ward = form['ward']
        respondent.created_by = user
        respondent.save()
        checkPrior = KeyPopulationStatus.objects.filter(respondent=respondent)
        if checkPrior:
            for type in checkPrior:
                type.delete()
        if form['kp_status'] and len(form['kp_status']) > 0:
            for type in form['kp_status']:
                kp = KeyPopulationStatus(respondent = respondent, kp_status=type)
                kp.save()
        return JsonResponse({'status': 'success', 'redirect_id': respondent.id})

class GetList(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = RespondentSerializer

    def get_queryset(self):
        user = self.request.user
        role = getattr(user, 'role', None)
        organization = getattr(user, 'organization', None)

        if not role or not organization:
            raise PermissionDenied(
                'You are not associated with a role at an organization, and therefore do not have rights to view respondents. '
                'If you believe this is an error, please check with your supervisor or a site admin.'
            )
        return Respondent.objects.all()

class GetRespondentDetail(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request, pk):
        respondent = Respondent.objects.filter(id=pk).first()
        data = model_to_dict(respondent)

        #get age range for all respondents
        if not data['age_range']:
            data['age_range'] = respondent.get_age_range()
        data['uuid'] = str(respondent.uuid)

        #get kp status (if applicable)
        kp_status = []
        kpStatusObjects = KeyPopulationStatus.objects.filter(respondent=respondent)
        if kpStatusObjects:
            for kp in kpStatusObjects:
                kp_status.append(kp.kp_status)
        data['kp_status'] = kp_status

        #get pregnancy & HIV information (if applicable)
        pregnancy = Pregnancy.objects.filter(respondent=respondent).order_by('term_began')
        if pregnancy:
            data['pregnancy'] = pregnancy[0].is_pregnant
            data['pregnancy_began'] = pregnancy[0].term_began
        else:
            data['pregnancy'] = False
            data['pregnancy_began'] = None
        hivStatus = HIVStatus.objects.filter(respondent=respondent).first()
        if hivStatus:
            data['hiv_status'] = hivStatus.hiv_positive
        else:
            data['hiv_status'] = False
        return JsonResponse(data, safe=False)

class NewInteraction(APIView):
    permission_classes = [IsAuthenticated]
    def post(self, request):
        from projects.models import Project, Task
        from indicators.models import Indicator, IndicatorSubcategory
        messages = []
        user=request.user
        org = user.organization
        if not org:
            return
        data = json.loads(request.body)
        respondent = Respondent.objects.filter(id=data['respondent']).first()
        task = Task.objects.filter(id=data['task']).first()
        if not respondent or not task:
            messages.append('Incorrect information submitted. Please double check these fields')
            return JsonResponse({'status': 'warning', 'message': messages })
        try:
            datetime.strptime(data['date'], '%Y-%m-%d')
        except ValueError:
            messages.append(f'Interaction date is not a valid date. Please double check this field.')
            return JsonResponse({'status': 'warning', 'message': messages })
        date = datetime.strptime(data['date'], "%Y-%m-%d").date()
        project = Project.objects.filter(id=task.project.id).first()
        if date > project.end or date < project.start:
            messages.append(f'Interaction date should be within project range (between {project.start} and {project.end}).')
            return JsonResponse({'status': 'warning', 'message': messages })
        if data['prerequisite']:
            prereq = Interaction.objects.filter(id=data['prerequisite']).first()
            if not prereq:
                messages.append(f'Invalid prerequisite interaction.')
                return JsonResponse({'status': 'warning', 'message': messages })
        else:
            prereq = None
        if data['categories']:
            for category in data['categories']:
                category = IndicatorSubcategory.objects.filter(id=category).first()
                if not category:
                    messages.append(f'Category {category} is not valid. Please double check this field.')
                    return JsonResponse({'status': 'warning', 'message': messages })
                interaction = Interaction(respondent=respondent, task=task, interaction_date=data['date'], created_by=user, subcategory=category, prerequisite=prereq)
                interaction.save() 
        else:
            interaction = Interaction(respondent=respondent, task=task, interaction_date=data['date'], created_by=user, prerequisite=prereq)
            interaction.save()
        return JsonResponse({'status': 'success', 'message': [f'Interaction saved! Good work!']})

