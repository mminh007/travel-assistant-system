$(document).ready(function() {
    // Cancel Booking Logic
    $('.btn-cancel').on('click', function(e) {
        e.preventDefault();
        var btn = $(this);
        var bookingId = btn.data('id');

        if (!confirm('Are you sure you want to cancel this booking? This action cannot be undone.')) {
            return;
        }

        var originalHtml = btn.html();
        btn.prop('disabled', true).html('<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Canceling...');

        $.ajax({
            url: '/api/booking/cancel/' + bookingId,
            type: 'POST',
            success: function(response) {
                if (response.success) {
                    // Remove the card with animation
                    var cardWrapper = $('#booking-' + bookingId);
                    cardWrapper.fadeOut(400, function() {
                        $(this).remove();
                        // Optional: Check if empty and show empty state
                    });
                }
            },
            error: function(xhr) {
                alert('Failed to cancel the booking. It might be past the 24-hour limit.');
                btn.prop('disabled', false).html(originalHtml);
            }
        });
    });

    // Pay Booking Logic
    $('.btn-pay').on('click', function(e) {
        e.preventDefault();
        var btn = $(this);
        var bookingId = btn.closest('.booking-card-wrapper').attr('id').replace('booking-', '');

        var originalHtml = btn.html();
        btn.prop('disabled', true).html('<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Processing...');

        $.ajax({
            url: '/api/Payment/pay-pending-booking/' + bookingId,
            type: 'POST',
            success: function(response) {
                if (response.url) {
                    window.location.href = response.url;
                }
            },
            error: function(xhr) {
                alert('Failed to initialize payment. Please try again later.');
                btn.prop('disabled', false).html(originalHtml);
            }
        });
    });
});
