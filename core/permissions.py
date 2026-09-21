"""Role-based access helpers shared by every app (synopsis §12: role-based access)."""

from functools import wraps

from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect

from accounts.models import Role


def _check(user, roles):
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return user.role in roles


def role_required(*roles):
    """Decorator restricting a function view to the given roles."""

    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect("accounts:login")
            if not _check(request.user, roles):
                raise PermissionDenied("Your role does not have access to this page.")
            return view_func(request, *args, **kwargs)

        return _wrapped

    return decorator


admin_required = role_required(Role.ADMIN)
dentist_required = role_required(Role.DENTIST)
patient_required = role_required(Role.PATIENT)
staff_required = role_required(Role.ADMIN, Role.DENTIST)


class RoleRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Class-based-view counterpart of ``role_required``."""

    allowed_roles: tuple = ()

    def test_func(self):
        return _check(self.request.user, self.allowed_roles)

    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return super().handle_no_permission()
        raise PermissionDenied("Your role does not have access to this page.")


class AdminRequiredMixin(RoleRequiredMixin):
    allowed_roles = (Role.ADMIN,)


class DentistRequiredMixin(RoleRequiredMixin):
    allowed_roles = (Role.DENTIST,)


class PatientRequiredMixin(RoleRequiredMixin):
    allowed_roles = (Role.PATIENT,)


class StaffRequiredMixin(RoleRequiredMixin):
    """Admin or dentist -- anyone who works at the clinic."""

    allowed_roles = (Role.ADMIN, Role.DENTIST)
