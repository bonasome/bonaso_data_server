from django.db import models
from django.contrib.auth import get_user_model
User = get_user_model()

class Organization(models.Model):
    '''
    Organizations are the a useful model for linking users together and determining which users should
    see waht content. That said, its a fairly simple model mostly used for linking. The only required
    field is a name. 

    Other information can be collected and stored for convenience/reference.
    '''
    name = models.CharField(max_length=255, verbose_name='Organization Name')
    full_name = models.CharField(max_length=255, verbose_name='Full/Extended Organization Name', blank=True, null=True)
    description = models.TextField(null=True, blank=True, verbose_name='Description')
    office_address = models.CharField(max_length=255, verbose_name='Office Address', null=True, blank=True)
    office_email = models.EmailField(verbose_name='Office Email Address', null=True, blank=True)
    office_phone = models.CharField(max_length=255, verbose_name='Office Phone Number', null=True, blank=True)
    executive_director = models.CharField(max_length=255, verbose_name='Name of Executive Director', null=True, blank=True)
    ed_email = models.EmailField(verbose_name='Exeuctive Director Email Address', null=True, blank=True)
    ed_phone = models.CharField(max_length=255, verbose_name='Exeuctive Director Phone Number', null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='organization_created_by')
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='organization_updated_by')

    def __str__(self):
        return self.name