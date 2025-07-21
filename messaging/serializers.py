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

            if org != user.organization:
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
    recipient_data = serializers.ListField(
        child=serializers.DictField(),
        required=True,
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
        if not send_to_admin and not recipient_data:
            raise serializers.ValidationError('Message must have at least one recipient')
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

        if send_to_admin:
            admin_users = User.objects.filter(role='admin')
            for admin in admin_users:
                if not any(rec.get('id') == admin.id for rec in recipients_data):
                    recipients_data.append({'id': admin.id, 'actionable': True})

        seen = set()

        for recipient in recipients_data:
            rid = recipient.get('id')
            if rid in seen:
                continue 
            seen.add(rid)
            MessageRecipient.objects.create(
                message=message,
                recipient_id=recipient.get('id'),
                actionable=recipient.get('actionable', False)
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

        if recipient_updates:
            for rec in recipient_updates:
                mr = MessageRecipient.objects.filter(message=instance, recipient_id=rec.get('id')).first()
                if mr:
                    mr.actionable = rec.get('actionable', False)
                    mr.save()
                else:
                    raise serializers.ValidationError('Cannot change participants in an active thread.')