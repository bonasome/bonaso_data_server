from rest_framework import serializers
from messaging.models import Message, MessageRecipient, Announcement
from projects.serializers import ProjectListSerializer
from projects.models import Project
from organizations.models import Organization
from organizations.serializers import OrganizationListSerializer
from rest_framework.exceptions import PermissionDenied
from django.contrib.auth import get_user_model
User = get_user_model()

class AnnouncementSerializer(serializers.ModelSerializer):
    project = ProjectListSerializer(read_only=True)
    organization = OrganizationListSerializer(read_only=True)
    project_id = serializers.PrimaryKeyRelatedField(queryset=Project.objects.all(), write_only=True, required=False)
    organization_id = serializers.PrimaryKeyRelatedField(queryset=Organization.objects.all(), write_only=True)

    class Meta:
        model = Announcement
        fields = [
            'subject', 'body', 'sent_by', 'sent_on',
            'project', 'project_id', 'organization', 'organization_id',
            'cascade_to_children'
        ]
        read_only_fields = ['sent_by', 'sent_on']

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
    class Meta:
        model=MessageRecipient
        fields = [
            'message', 'recipient', 'read', 'actionable', 'completed', 'deleted_by_recipient'
        ]
class MessageSerializer(serializers.ModelSerializer):
    recipients = MessageRecipientSerializer(source='recipient_links', many=True, read_only=True)
    recipient_ids = serializers.PrimaryKeyRelatedField(queryset=User.objects.all(), many=True, write_only=True)
    class Meta:
        model = Message
        fields = [
            'subject', 'sender', 'body', 'sent_on', 'parent', 'deleted_by_sender', 'recipients', 'send_to_admin',
        ]
    def validate(self, attrs):
        send_to_admin = attrs.get('send_to_admin', False)
        recipient_ids = self.initial_data.get('recipient_ids', [])

        if not send_to_admin and not recipient_ids:
            raise serializers.ValidationError('Message must have at least one recipient')

    def create(self, validated_data):
        recipient_ids = self.initial_data.get('recipient_ids', [])
        send_to_admin = self.initial_data.get('send_to_admin', False)
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
                recipient_id=recipient_id
            )

        return message 
        