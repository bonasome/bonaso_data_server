from rest_framework import serializers
from indicators.models import Indicator, IndicatorSubcategory

class IndicatorSubcategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = IndicatorSubcategory
        fields = ['name']

class IndicatorListSerializer(serializers.ModelSerializer):
    class Meta:
        model=Indicator
        fields = ['id', 'code', 'name']

class PrerequisiteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Indicator
        fields = ['id', 'code', 'name']

class IndicatorSerializer(serializers.ModelSerializer):
    subcategories = IndicatorSubcategorySerializer(many=True, read_only=True)
    subcategory_names = serializers.ListField(
        child=serializers.CharField(), write_only=True, required=False
    )
    prerequisite = PrerequisiteSerializer(read_only=True)
    prerequisite_id = serializers.PrimaryKeyRelatedField(
        source='prerequisite',
        queryset=Indicator.objects.all(),
        write_only=True,
        required=False, 
        allow_null=True,
    )
    class Meta:
        model = Indicator
        fields = ['id', 'name', 'code', 'prerequisite', 'prerequisite_id', 'description', 'subcategories', 
                  'subcategory_names', 'require_numeric', 'status']

    def validate(self, attrs):
        code = attrs.get('code', getattr(self.instance, 'code', None))
        name = attrs.get('name', getattr(self.instance, 'name', None))
        if not code:
            raise serializers.ValidationError({"code": "Code is required."})
        if not name:
            raise serializers.ValidationError({"name": "Name is required."})
        # Uniqueness check for 'code'
        qs = Indicator.objects.filter(code=code)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError({"code": "Code must be unique."})
        # Uniqueness check for 'name'
        qs = Indicator.objects.filter(name=name)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError({"name": "Name must be unique."})
        return attrs
    
    def create(self, validated_data):
        subcategory_names = validated_data.pop('subcategory_names', [])
        indicator = Indicator.objects.create(**validated_data)
        subcategories = [
            IndicatorSubcategory.objects.get_or_create(name=name)[0]
            for name in subcategory_names
        ]
        indicator.subcategories.set(subcategories)
        return indicator

    def update(self, instance, validated_data):
        subcategory_names = validated_data.pop('subcategory_names', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if subcategory_names is not None:
            subcategories = [
                IndicatorSubcategory.objects.get_or_create(name=name)[0]
                for name in subcategory_names
            ]
            instance.subcategories.set(subcategories)
        return instance