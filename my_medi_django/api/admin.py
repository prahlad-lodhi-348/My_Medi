from django.contrib import admin
from .models import User, Medicine, Profile,Regimen,RegimenMedicine,DoseTime,Stock,IntakeLog,Caregiver

admin.site.register(User)
admin.site.register(Medicine)
admin.site.register(Profile)
admin.site.register(Regimen)
admin.site.register(RegimenMedicine)
admin.site.register(DoseTime)
admin.site.register(Stock)
admin.site.register(IntakeLog)
admin.site.register(Caregiver)
# admin has acces to all the models and can perform CRUD operations on them.
