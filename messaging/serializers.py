from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied

from messaging.models import Message, MessageRecipient, Announcement, Alert, AlertRecipient, AnnouncementOrganization, AnnouncementRecipient
from projects.models import Project
from projects.serializers import ProjectListSerializer
from projects.utils import ProjectPermissionHelper
from organizations.models import Organization
from profiles.serializers import ProfileListSerializer

from django.utils.timezone import now
from django.contrib.auth import get_user_model
User = get_user_model()

class AlertSerializer(serializers.ModelSerializer):
    '''
    Allow for viewing alerts. User's do not create events since they are always system generated.
    '''
    content_object = serializers.SerializerMethodField()
    read = serializers.SerializerMethodField(read_only=True)
    def get_read(self, obj):
        return AlertRecipient.objects.filter(alert=obj, recipient=self.context['request'].user, read=True).exists()
    
    def get_content_object(self, obj):
        if obj.content_object:
            return str(obj.content_object)
        return None
    
    class Meta: 
        model=Alert
        fields = ['id', 'alert_type', 'sent_on', 'subject', 'body', 'content_object', 'object_id', 'read']

class AnnouncementSerializer(serializers.ModelSerializer):
    '''
    Allow for viewing/creating/editing an announcement
    '''
    project = ProjectListSerializer(read_only=True)
    project_id = serializers.PrimaryKeyRelatedField(queryset=Project.objects.all(), write_only=True, required=False, allow_null=True, source='project')
    organization_ids = serializers.PrimaryKeyRelatedField(queryset=Organization.objects.all(), write_only=True, required=False, many=True, source='organizations')
    sent_by = ProfileListSerializer(read_only=True)
    read = serializers.SerializerMethodField(read_only=True)
    
    def get_read(self, obj):
        #read data is created by creating a new row in the recipient table
        return AnnouncementRecipient.objects.filter(announcement=obj, recipient=self.context['request'].user).exists()
    
    class Meta:
        model = Announcement
        fields = [
            'id', 'subject', 'body', 'sent_by', 'sent_on', 'read',
            'project', 'project_id', 'organizations', 'organization_ids',
            'cascade_to_children', 'visible_to_all'
        ]
        read_only_fields = ['sent_by', 'sent_on', 'id', 'read']

    def validate(self, attrs):
        user = self.context['request'].user
        project = attrs.get('project')
        if user.role not in ['admin', 'manager', 'meofficer']:
            raise PermissionDenied('You do not have permission to write announcements.')
        if user.role == 'admin':
            return attrs
        #admins can create any announcement
        if user.role != 'admin':
            #else it needs to be scoped to a project/org
            if not project:
                raise PermissionDenied('You must provide a project.')
            #import project helpers to manage this --> see projects.utils
            perm_manager = ProjectPermissionHelper(user=user, project=project)
            result = perm_manager.alter_switchboard(data=attrs, instance=(self.instance if self.instance else None))
            if not result.get('success', False):
                raise PermissionDenied(result.get('data'))
        return result['data']

    def _set_organizations(self, announcement, organizations):
        '''
        Set the organizations attached to this announcement. Clear existing on update
        '''
        AnnouncementOrganization.objects.filter(announcement=announcement).delete()
        orgs = organizations
        links = [
            AnnouncementOrganization(announcement=announcement, organization=org)
            for org in orgs
        ]
        AnnouncementOrganization.objects.bulk_create(links)

    def create(self, validated_data):
        user = self.context.get('request').user if self.context.get('request') else None
        organizations = validated_data.pop('organizations', [])
        announcement = Announcement.objects.create(**validated_data)
        self._set_organizations(announcement, organizations)
        announcement.sent_by = user
        announcement.save()
        return announcement
    
    def update(self, instance, validated_data):
        user = self.context.get('request').user if self.context.get('request') else None
        organizations = validated_data.pop('organizations', [])

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.updated_by = user
        instance.save()
        if 'organization_ids' in self.initial_data: 
            self._set_organizations(instance, organizations)
        return instance


class MessageRecipientSerializer(serializers.ModelSerializer):
    '''
    Nested serialzier for providing information about message recipients (names, read, etc.)
    '''
    recipient = ProfileListSerializer(read_only=True)
    class Meta:
        model=MessageRecipient
        fields = [
            'id', 'message', 'recipient', 'read', 'actionable', 'completed', 'deleted_by_recipient'
        ]

class ReplySerializer(serializers.ModelSerializer):
    '''
    Another nested serializer for replies (messages with a parent)
    '''
    sender = ProfileListSerializer(read_only=True)
    recipients = MessageRecipientSerializer(read_only=True, many=True, source='recipient_links')
    class Meta:
        model=Message
        fields = ['id', 'subject', 'body', 'sender', 'recipients', 'sent_on']

class MessageSerializer(serializers.ModelSerializer):
    '''
    Main serializer for a messaging threat thread.
    '''
    sender = ProfileListSerializer(read_only=True)
    recipients = MessageRecipientSerializer(source='recipient_links', many=True, read_only=True)
    recipient_data = serializers.ListField(
        child=serializers.DictField(),
        required=False,
        write_only=True
    )
    replies = serializers.SerializerMethodField()

    def get_replies(self, obj):
        queryset = Message.objects.filter(parent=obj, deleted_by_sender=False)
        serializer = ReplySerializer(queryset, many=True)
        return serializer.data
    
    class Meta:
        model = Message
        fields = [
            'id', 'subject', 'sender','body', 'sent_on', 'parent','deleted_by_sender', 
            'recipients', 'recipient_data', 'send_to_admin', 'deleted_by_sender',
            'replies',
        ]
    def validate(self, attrs):
        if attrs.get('deleted_by_sender'):
            return attrs
        send_to_admin = attrs.get('send_to_admin', False)
        recipient_data = attrs.get('recipient_data', [])
        parent = attrs.get('parent', None)
        subject = attrs.get('subject')
        #make sure there is at least one recipient
        if not send_to_admin and not recipient_data:
            raise serializers.ValidationError('Message must have at least one recipient')
        #make sure the message has a subject unless its a reply (in which case it inherits the parents)
        if not parent and not subject:
            raise serializers.ValidationError('Non-replies must have a subject.')
        return attrs
    
    def validate_recipient_data(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError("recipient_data must be a list.")
        for item in value:
            if not isinstance(item, dict) or 'id' not in item:
                raise serializers.ValidationError("Each item must be a dict with at least an 'id'.")
        return value
    
    def create(self, validated_data):
        recipients_data = validated_data.pop('recipient_data', [])
        send_to_admin = validated_data.pop('send_to_admin', False)
        user = self.context['request'].user

        message = Message.objects.create(
            sender=user,
            subject=validated_data.get('subject'),
            body=validated_data.get('body'),
            parent=validated_data.get('parent'),
        )
        #if send to admin, automatically populate the recipients to include all admins
        if send_to_admin:
            admin_users = User.objects.filter(role='admin')
            for admin in admin_users:
                if not any(rec.get('id') == admin.id for rec in recipients_data):
                    recipients_data.append({'id': admin.id, 'actionable': True})
        seen = set()

        #get recipient data, expected as a dict of {id: int, actionable: bool}
        for recipient in recipients_data:
            rid = recipient.get('id')
            if rid in seen:
                continue #prevent dupicate recipients
            seen.add(rid)
            MessageRecipient.objects.create(
                message=message,
                recipient_id=recipient.get('id'),
                actionable=recipient.get('actionable', False) #assign actionable status
            )

        return message
    
    def update(self, instance, validated_data):
        # Recipients are immutable by current policy
        if validated_data.pop('deleted_by_sender', None):
            instance.deleted_by_sender = True
            instance.save()
            return instance

        recipient_updates = validated_data.pop('recipient_data', [])

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        instance.edited_on = now()
        instance.save()

        #allow for users to update recipients actionable status, but not change recipient list
        if recipient_updates:
            for rec in recipient_updates:
                mr = MessageRecipient.objects.filter(message=instance, recipient_id=rec.get('id')).first()
                if mr:
                    mr.actionable = rec.get('actionable', False)
                    mr.save()
                else:
                    raise serializers.ValidationError('Cannot change participants in an active thread.')
        return instance