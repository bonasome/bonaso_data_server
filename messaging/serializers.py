from rest_framework import serializers
from messaging.models import Message, MessageRecipient, Announcement, Alert
from projects.serializers import ProjectListSerializer
from projects.models import Project
from organizations.models import Organization
from organizations.serializers import OrganizationListSerializer
from profiles.serializers import ProfileListSerailizer
from rest_framework.exceptions import PermissionDenied
from django.utils.timezone import now
from django.contrib.auth import get_user_model
User = get_user_model()

class AlertSerializer(serializers.ModelSerializer):
    content_object = serializers.SerializerMethodField()

    def get_content_object(self, obj):
        if obj.content_object:
            return str(obj.content_object)  # or access specific fields
        return None
    
    class Meta: 
        model=Alert
        fields = ['id', 'alert_type', 'sent_on', 'subject', 'body', 'content_object', 'object_id']

class AnnouncementSerializer(serializers.ModelSerializer):
    project = ProjectListSerializer(read_only=True)
    organization = OrganizationListSerializer(read_only=True)
    project_id = serializers.PrimaryKeyRelatedField(queryset=Project.objects.all(), write_only=True, required=False)
    organization_id = serializers.PrimaryKeyRelatedField(queryset=Organization.objects.all(), write_only=True, required=False)

    class Meta:
        model = Announcement
        fields = [
            'id', 'subject', 'body', 'sent_by', 'sent_on',
            'project', 'project_id', 'organization', 'organization_id',
            'cascade_to_children'
        ]
        read_only_fields = ['sent_by', 'sent_on', 'id']

    def validate(self, attrs):
        user = self.context['request'].user
        project = attrs.get('project_id')
        org = attrs.get('organization_id')

        if user.role not in ['admin', 'manager', 'meofficer']:
            raise serializers.PermissionDenied('You do not have permission to write announcements.')

        if user.role != 'admin':
            if project:
                raise serializers.PermissionDenied('You do not have permission to write announcements for a project.')
            if not org:
                raise serializers.ValidationError('You must select an organization to write an announcement.')

            if org != user.organization and org.parent_organization != user.organization:
                raise serializers.PermissionDenied('You do not have permission to target this organization.')

        return attrs

    def create(self, validated_data):
        validated_data['sent_by'] = self.context['request'].user
        return super().create(validated_data)


class MessageRecipientSerializer(serializers.ModelSerializer):
    recipient = ProfileListSerailizer(read_only=True)
    class Meta:
        model=MessageRecipient
        fields = [
            'id', 'message', 'recipient', 'read', 'actionable', 'completed', 'deleted_by_recipient'
        ]
class ReplySerializer(serializers.ModelSerializer):
    sender = ProfileListSerailizer(read_only=True)
    recipients = MessageRecipientSerializer(read_only=True, many=True, source='recipient_links')
    class Meta:
        model=Message
        fields = ['id', 'subject', 'body', 'sender', 'recipients']

class MessageSerializer(serializers.ModelSerializer):
    sender = ProfileListSerailizer(read_only=True)
    recipients = MessageRecipientSerializer(source='recipient_links', many=True, read_only=True)
    recipient_ids = serializers.PrimaryKeyRelatedField(queryset=User.objects.all(), many=True, write_only=True)
    replies = serializers.SerializerMethodField()
    actionable = serializers.BooleanField(allow_null=True)
    def get_replies(self, obj):
        queryset = Message.objects.filter(parent=obj, deleted_by_sender=False)
        serializer = ReplySerializer(queryset, many=True)
        return serializer.data
    class Meta:
        model = Message
        fields = [
            'id', 'subject', 'sender','body', 'sent_on', 'parent','deleted_by_sender', 
            'recipients', 'recipient_ids', 'send_to_admin', 'deleted_by_sender',
            'replies', 'actionable'
        ]
    def validate(self, attrs):
        if attrs.get('deleted_by_sender'):
            return attrs
        send_to_admin = attrs.get('send_to_admin', False)
        recipient_ids = self.initial_data.get('recipient_ids', [])
        parent = self.initial_data.get('parent', None)
        subject = attrs.get('subject')
        if not send_to_admin and not recipient_ids:
            raise serializers.ValidationError('Message must have at least one recipient')
        if not parent and not subject:
            raise serializers.ValidationError('Non-replies must have a subject.')
        return attrs
    
    def create(self, validated_data):
        recipient_ids = self.initial_data.get('recipient_ids', [])
        send_to_admin = self.initial_data.get('send_to_admin', False)
        #for now, this will apply to all members of a threat
        actionable = self.validated_data.get('actionable', False)
        user = self.context['request'].user

        message = Message.objects.create(
            sender=user,
            subject=validated_data['subject'],
            body=validated_data['body'],
            parent=validated_data.get('parent'),
        )

        if send_to_admin:
            recipient_ids += [admin.id for admin in User.objects.filter(role='admin').all()]
        for recipient_id in recipient_ids:
            MessageRecipient.objects.create(
                message=message,
                recipient_id=recipient_id,
                actionable=actionable
            )

        return message 
    def update(self, instance, validated_data):
        #currently the idea is that once a thread is established, its recipients are immutable, though this may change later
        if validated_data.pop('deleted_by_sender', None):
            instance.deleted_by_sender = True
            instance.save()
            return instance
        actionable = self.validated_data.get('actionable', False)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.edited_on = now()
        mr = MessageRecipient.objects.filter(message=instance)
        print(actionable)
        mr.update(actionable=actionable)
        instance.save()

        return instance