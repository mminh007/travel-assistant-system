$(document).ready(function() {
    const $checkoutBtn = $('#checkout-btn');
    const $guestForm = $('#guest-details-form');
    
    // Initialize Stripe
    const stripe = Stripe(stripePublishableKey);
    let checkoutSession = null;

    $checkoutBtn.on('click', async function(e) {
        e.preventDefault();

        // Validate form
        const guestFormEl = $guestForm[0];
        if (!guestFormEl.checkValidity()) {
            guestFormEl.reportValidity();
            return;
        }

        const btnOriginalText = $checkoutBtn.html();
        $checkoutBtn.html('<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Processing...');
        $checkoutBtn.prop('disabled', true);

        try {
            // Get data from button and form
            const roomTypeId = $checkoutBtn.data('room-id');
            const checkIn = $checkoutBtn.data('check-in');
            const checkOut = $checkoutBtn.data('check-out');
            const guests = parseInt($checkoutBtn.data('guests')) || 1;

            const guestName = $('#guestName').val();
            const guestEmail = $('#guestEmail').val();
            const phoneNumber = $('#phoneNumber').val();
            const specialRequests = $('#specialRequests').val();

            const requestBody = {
                roomTypeId: roomTypeId,
                checkIn: checkIn,
                checkOut: checkOut,
                guests: guests,
                guestName: guestName,
                guestEmail: guestEmail,
                phoneNumber: phoneNumber,
                specialRequests: specialRequests
            };

            const token = localStorage.getItem('token');

            const response = await $.ajax({
                url: '/api/payment/create-checkout-session',
                type: 'POST',
                contentType: 'application/json',
                headers: {
                    'Authorization': `Bearer ${token}`
                },
                data: JSON.stringify(requestBody)
            });

            const clientSecret = response.clientSecret;

            if (checkoutSession) {
                checkoutSession.destroy(); // Destroy previous instance if any
            }

            // Initialize Embedded Checkout
            checkoutSession = await stripe.initEmbeddedCheckout({
                clientSecret,
            });

            // Mount to the DOM
            checkoutSession.mount('#checkout');

            // Show modal
            const paymentModal = new bootstrap.Modal($('#paymentModal')[0]);
            paymentModal.show();

        } catch (error) {
            console.error('Checkout error:', error);
            if (error.status === 401) {
                alert('Please log in to continue.');
                window.location.href = '/Account/Login';
            } else {
                alert('There was an error initializing the payment. Please try again.');
            }
        } finally {
            $checkoutBtn.html(btnOriginalText);
            $checkoutBtn.prop('disabled', false);
        }
    });
});
