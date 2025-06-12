from django.db import models

class Organization(models.Model):
    name = models.CharField(max_length=255, verbose_name='Organization Name')
    parent_organization = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Parent Organization')
    office_address = models.CharField(max_length=255, verbose_name='Office Address', null=True, blank=True)
    office_email = models.EmailField(verbose_name='Office Email Address', null=True, blank=True)
    office_phone = models.CharField(max_length=255, verbose_name='Office Phone Number', null=True, blank=True)
    executive_director = models.CharField(max_length=255, verbose_name='Name of Executive Director', null=True, blank=True)
    ed_email = models.EmailField(verbose_name='Exeuctive Director Email Address', null=True, blank=True)
    ed_phone = models.CharField(max_length=255, verbose_name='Exeuctive Director Phone Number', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

