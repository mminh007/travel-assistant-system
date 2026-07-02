$(document).ready(function() {
    // Initialize date range picker
    $("#dateRangePicker").flatpickr({
        mode: "range",
        minDate: "today",
        dateFormat: "Y-m-d",
        showMonths: 2
    });

    // Guest picker logic
    let guests = { adults: 2, children: 0, rooms: 1 };

    function updateGuestInput() {
        let text = `${guests.adults} adults · ${guests.children} children · ${guests.rooms} room${guests.rooms > 1 ? 's' : ''}`;
        $('#guestInput').val(text);
        
        $('#adultCount').text(guests.adults);
        $('#childCount').text(guests.children);
        $('#roomCount').text(guests.rooms);

        $('button[data-type="adults"][data-action="minus"]').prop('disabled', guests.adults <= 1);
        $('button[data-type="children"][data-action="minus"]').prop('disabled', guests.children <= 0);
        $('button[data-type="rooms"][data-action="minus"]').prop('disabled', guests.rooms <= 1);
    }

    $('.guest-btn').on('click', function(e) {
        e.preventDefault();
        let type = $(this).data('type');
        let action = $(this).data('action');
        
        if(action === 'plus') {
            guests[type]++;
        } else {
            if(guests[type] > 0) guests[type]--;
        }
        updateGuestInput();
    });

    $('#btnDoneGuest').on('click', function() {
        var dropdownEl = $('#guestInput')[0];
        var dropdown = bootstrap.Dropdown.getInstance(dropdownEl);
        if (dropdown) {
            dropdown.hide();
        }
    });
    
    updateGuestInput();
});
