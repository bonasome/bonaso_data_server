from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views import View
from django.forms.models import model_to_dict
from rest_framework.viewsets import ModelViewSet
from rest_framework import filters
from rest_framework.response import Response
from users.restrictviewset import RoleRestrictedViewSet
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from django.utils.dateparse import parse_date
import json
from datetime import datetime, date
today = date.today().isoformat()

from respondents.models import Respondent, Interaction, Pregnancy, HIVStatus
from respondents.serializers import RespondentSerializer, RespondentListSerializer, InteractionSerializer

class RespondentViewSet(RoleRestrictedViewSet):
    from rest_framework.filters import OrderingFilter
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter, OrderingFilter]
    ordering_fields = ['name','start', 'end', 'client']
    search_fields = ['first_name', 'last_name', 'uuid', 'comments', 'village'] 
    queryset = Respondent.objects.all()
    serializer_class = RespondentSerializer
    def get_serializer_class(self):
        if self.action == 'list':
            return RespondentListSerializer
        else:
            return RespondentSerializer
    def perform_create(self, serializer):
        respondent = serializer.save(created_by=self.request.user)
        data = self.request.data
        is_pregnant = data.get('is_pregnant')
        start = data.get('term_began')
        end = data.get('term_ended')

        if is_pregnant in ['true', 'True', True, '1']:
            is_pregnant = True
        else:
            is_pregnant = False

        if is_pregnant and not start:
            start = today
        elif not is_pregnant and start and not end:
            end = today
        elif is_pregnant and end:
            is_pregnant = False
        checkUnended = False
        if is_pregnant and start and not end:
            checkUnended = Pregnancy.objects.filter(respondent=respondent, term_ended__isnull=True).first()
        if not checkUnended:
            pregnancy = Pregnancy.objects.create(respondent=respondent, is_pregnant=is_pregnant, term_began=start, term_ended = end)
        
        hiv_positive = data.get('hiv_positive')
        date_positive = data.get('positive_since')
        if hiv_positive in ['true', 'True', True, '1']:
            hiv_positive = True
        else:
            hiv_positive = False

        existing_status = HIVStatus.objects.filter(respondent=respondent).first()
        if existing_status:
            if existing_status.hiv_positive and not hiv_positive:
                existing_status.hiv_positive = False
                existing_status.date_positive = None
                existing_status.save()
        else:
            HIVStatus.objects.create(
                respondent=respondent,
                hiv_positive=hiv_positive,
                date_positive=date_positive if hiv_positive else None
            )

class InteractionViewSet(RoleRestrictedViewSet):
    permission_classes = [IsAuthenticated]
    queryset = Interaction.objects.all()
    serializer_class = InteractionSerializer
    filterset_fields = ['task', 'respondent']
    def get_queryset(self):
        from projects.models import Task, Project
        queryset = super().get_queryset()

        start = self.request.query_params.get('start')
        end = self.request.query_params.get('end')
        if start:
            queryset = queryset.filter(interaction_date__gte=start)
        if end:
            queryset = queryset.filter(interaction_date__lte=end)
        return queryset
    def create(self, request, *args, **kwargs):
        from projects.models import Task
        from organizations.models import Organization
        user = request.user
        role = getattr(user, 'role', None)
        org = getattr(user, 'organization', None)
        data = request.data
        
        try:
            respondent = Respondent.objects.get(id=data.get('respondent'))
            task = Task.objects.get(id=data.get('task'))
            
            if role != 'admin':
                if task.organization != org:
                    return Response({'detail': 'Invalid task: not part of your organization.'}, status=400)
            interaction_date=data.get('interaction_date')
            interaction_date = parse_date(interaction_date)
            if not interaction_date:
                return Response({'detail': 'Invalid date format.'}, status=400)
            
            number_required = task.indicator.require_numeric
            number = data.get('numeric_component')
            if number_required:
                # Check if value is present and can be converted to an int
                try:
                    if number is None or number == '':
                        raise ValueError
                    number = int(number)
                except (ValueError, TypeError):
                    return Response({'detail': 'Interaction expected a valid number.'}, status=400)

            else:
                # If number is provided when it's not required
                if number not in [None, '', 0, '0']:
                    return Response({'detail': 'Interaction did not expect a number.'}, status=400)
            
            subcategories = data.get('subcategories', [])
            if task.indicator.subcategories.exists():
                if not subcategories:
                    return Response({'detail': 'Interaction subcategories may not be empty.'}, status=400)

            prereq = task.indicator.prerequisite
            if prereq:
                parent_interaction = Interaction.objects.filter(task__indicator=prereq, interaction_date__lte=interaction_date)
                if not parent_interaction.exists():
                    return Response({'detail': 'Task requires a prerequisite interaction.'}, status=400)
                most_recent_parent = parent_interaction.order_by('-interaction_date').first()
                if most_recent_parent.subcategories.exists():
                    parent_subcat_ids = set(most_recent_parent.subcategories.values_list('id', flat=True))
                    indicator_subcat_ids = set(task.indicator.subcategories.values_list('id', flat=True))

                    parent_subcats = set(most_recent_parent.task.indicator.subcategories.values_list('id', flat=True))
                    child_subcats = set(task.indicator.subcategories.values_list('id', flat=True))

                    if parent_subcats == child_subcats:
                        current_subcat_ids = set(subcategories)
                        if not current_subcat_ids.issubset(parent_subcat_ids):
                            return Response(
                                {'detail': 'Task requires prerequisite interaction to have corresponding subcategories.'},
                                status=400
                            )

        except (Respondent.DoesNotExist, Task.DoesNotExist):
            return Response({'detail': 'Respondent or Task not found.'}, status=400)
        
        interaction = Interaction.objects.create(
            respondent=respondent, 
            task =task, 
            interaction_date=data.get('interaction_date'), 
            created_by = user,
            numeric_component=number if number_required else None
        )
        subcategories = data.pop('subcategories', [])
        interaction.subcategories.set(subcategories)
        serializer = self.get_serializer(interaction)
        return Response(serializer.data, status=201)
    


'''
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
class RecordRespondent(APIView):
    permission_classes = [IsAuthenticated]
    def post(self, request):
        messages =[]
        user = request.user
        data = request.data
        form = data.get('formData', {})
        respondent = None
        isAnonymous = form.get('isAnonymous')
        if 'respondent_id' in form:
            checkRespondent = Respondent.objects.filter(id = form.get('respondent_id')).first()
            if checkRespondent:
                respondent = checkRespondent
                respondent.is_anonymous = isAnonymous
        else:
           idNo = form.get('id_no')
           checkRespondent =  Respondent.objects.filter(id_no = idNo).first()
           if checkRespondent:
               messages.append('A respondent with this id/passport number already exists. Please edit the existing respondent.')
               return JsonResponse({'status': 'warning', 'message': messages})
        if not respondent:
            respondent = Respondent(is_anonymous=isAnonymous)
        respondent.sex = form.get('sex')
        respondent.village = form.get('village')
        respondent.district = form.get('district')
        respondent.citizenship = form.get('citizenship')
        respondent.comments = form.get('comments')
        if isAnonymous:
            respondent.age_range = form.get('age_range')
            respondent.dob = None
            respondent.first_name = None
            respondent.last_name = None
            respondent.id_no = None
            respondent.email = None
            respondent.phone_number = None
            respondent.ward = None
        if not isAnonymous:
            if 'id_no' in form:
                respondent.id_no = form.get('id_no')
            respondent.dob = form.get('dob')
            respondent.first_name = form.get('first_name')
            respondent.last_name = form.get('last_name')
            respondent.email = form.get('email')
            respondent.phone_number = form.get('phone_number')
            respondent.ward = form.get('ward')
        respondent.created_by = user
        respondent.save()
        KeyPopulationStatus.objects.filter(respondent=respondent).delete()
        kpStats = form.get('kp_status', [])
        if kpStats and len(kpStats) > 0:
            for type in kpStats:
                kp = KeyPopulationStatus(respondent = respondent, kp_status=type)
                kp.save()
        return JsonResponse({'status': 'success', 'redirect_id': respondent.id})

class SetHIVStatus(APIView):
    permission_classes = [IsAuthenticated]
    def post(self, request):
        messages =[]
        user = request.user
        data = request.data
        respondent = Respondent.objects.filter(id=data.get('respondent')).first()
        if not respondent:
            return JsonResponse({'status': 'warning'})
        checkStatus = HIVStatus.objects.filter(respondent=respondent).first()
        if checkStatus:
            status = checkStatus
        else:
            status = HIVStatus(respondent = respondent)
        status.hiv_positive = data.get('hiv_positive')
        status.date_positive = data.get('date_positive')
        status.save()
        return JsonResponse({'status': 'success'})
class SetPregnancy(APIView):
    permission_classes = [IsAuthenticated]
    def post(self, request):
        messages =[]
        user = request.user
        data = request.data
        respondent = Respondent.objects.filter(id=data.get('respondent')).first()
        if not respondent:
            return JsonResponse({'status': 'warning'})
        checkPregnancy = Pregnancy.objects.filter(respondent=respondent, term_ended__isnull=True).first()
        if checkPregnancy:
            pregnancy = checkPregnancy
        else:
            pregnancy = Pregnancy(respondent = respondent)
        pregnancy.term_began = data.get('term_began')
        pregnancy.term_ended = data.get('term_ended')
        if pregnancy.term_ended:
            pregnancy.is_pregnant = False
        elif pregnancy.term_began:
            pregnancy.is_pregnant = True
        pregnancy.save()
        return JsonResponse({'status': 'success'})
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

class GetByID(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = GetByID

    def get_queryset(self):
        user = self.request.user
        role = getattr(user, 'role', None)
        organization = getattr(user, 'organization', None)

        if not role or not organization:
            raise PermissionDenied(
                'You are not associated with a role at an organization, and therefore do not have rights to view respondents. '
                'If you believe this is an error, please check with your supervisor or a site admin.'
            )
        pk = self.kwargs.get('pk')
        return Respondent.objects.filter(id=pk)
    
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
            data['hiv_status'] = hivStatus.date_positive
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
'''