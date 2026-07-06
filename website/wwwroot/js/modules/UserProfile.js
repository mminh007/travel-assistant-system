$(document).ready(function() {
    $('#userInfoForm').on('submit', function(e) {
        e.preventDefault();

        // Basic HTML5 validation check
        if (!this.checkValidity()) {
            e.stopPropagation();
            $(this).addClass('was-validated');
            return;
        }

        var btn = $('#btnUpdateProfile');
        var spinner = $('#updateSpinner');
        var alertBox = $('#updateAlert');

        btn.prop('disabled', true);
        spinner.removeClass('d-none');
        alertBox.addClass('d-none').removeClass('alert-success alert-danger');

        var data = {
            FullName: $('#FullName').val(),
            PhoneNumber: $('#PhoneNumber').val(),
            Address: $('#Address').val(),
            Nationality: $('#Nationality').val()
        };

        $.ajax({
            url: '/api/user/update-info',
            type: 'POST',
            contentType: 'application/json',
            data: JSON.stringify(data),
            success: function(response) {
                alertBox.text('Profile updated successfully!')
                        .addClass('alert-success d-block');
            },
            error: function(xhr) {
                alertBox.text('Failed to update profile. Please try again.')
                        .addClass('alert-danger d-block');
            },
            complete: function() {
                btn.prop('disabled', false);
                spinner.addClass('d-none');
                
                // Hide alert after 3 seconds
                setTimeout(function() {
                    alertBox.fadeOut(300, function() {
                        $(this).addClass('d-none').css('display', '');
                    });
                }, 3000);
            }
        });
    });
});
