from django.contrib import admin

from .models import Bill, BillItem, Payment


class BillItemInline(admin.TabularInline):
    model = BillItem
    extra = 1


class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 0


@admin.register(Bill)
class BillAdmin(admin.ModelAdmin):
    list_display = ("invoice_number", "patient", "issued_on", "status")
    list_filter = ("status", "issued_on")
    search_fields = ("invoice_number", "patient__user__first_name", "patient__patient_code")
    readonly_fields = ("invoice_number", "created_at", "updated_at")
    inlines = [BillItemInline, PaymentInline]


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("bill", "amount", "method", "paid_on")
    list_filter = ("method", "paid_on")
