$(document).ready(function() {
    $('.book-btn').on('click', function(e) {
        const roomId = $(this).data('room-id');
        const checkIn = $('#checkInDate').val();
        const checkOut = $('#checkOutDate').val();
        const guests = $('#guests').val();
        
        // Basic validation
        if (!checkIn || !checkOut) {
            alert('Please select check-in and check-out dates.');
            return;
        }
        
        if (new Date(checkIn) >= new Date(checkOut)) {
            alert('Check-out date must be after check-in date.');
            return;
        }

        // Redirect to the intermediate Confirmation page
        const confirmationUrl = `/Booking/Confirmation?roomTypeId=${roomId}&checkIn=${checkIn}&checkOut=${checkOut}&guests=${guests}`;
        window.location.href = confirmationUrl;
    });
});

window.updateAvailability = function() {
    // Just simple visual update or full page reload with params in a real scenario
    console.log("Update availability triggered. In a full app, this would refresh the table via AJAX.");
};
