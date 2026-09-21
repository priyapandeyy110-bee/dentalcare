from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .models import Notification


@login_required
def notification_list(request):
    queryset = request.user.notifications.all()
    if request.GET.get("filter") == "unread":
        queryset = queryset.filter(is_read=False)
    page = Paginator(queryset, 20).get_page(request.GET.get("page"))
    return render(
        request,
        "notifications/notification_list.html",
        {"page_obj": page, "active_filter": request.GET.get("filter", "all")},
    )


@login_required
def mark_read(request, pk):
    notification = get_object_or_404(Notification, pk=pk, recipient=request.user)
    notification.mark_read()
    if notification.link:
        return redirect(notification.link)
    return redirect("notifications:list")


@login_required
def mark_all_read(request):
    if request.method == "POST":
        updated = request.user.notifications.filter(is_read=False).update(
            is_read=True, read_at=timezone.now()
        )
        messages.success(request, "%s notifications marked as read." % updated)
    return redirect("notifications:list")
