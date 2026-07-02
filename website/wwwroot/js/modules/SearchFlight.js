$(document).ready(function () {

    // Initialize Date Range Picker
    const initDep = $('#initDepDate').val();
    const initRet = $('#initRetDate').val();
    
    let defaultDates = [];
    if (initDep) defaultDates.push(initDep);
    if (initRet) defaultDates.push(initRet);

    $("#flightDatePicker").flatpickr({
        mode: "range",
        minDate: "today",
        dateFormat: "Y-m-d",
        showMonths: 2,
        defaultDate: defaultDates
    });

    let currentFlightSort = 'best';

    function fetchFlights() {
        const origin = $('#originCode').val().toUpperCase();
        const destination = $('#destinationCode').val().toUpperCase();
        const dates = $('#flightDatePicker').val() || '';
        const adults = parseInt($('#adultCount').val()) || 1;

        if (!origin || !destination || !dates) {
            return;
        }

        let depDate = '';
        let retDate = null;
        
        if (dates.includes(' to ')) {
            const parts = dates.split(' to ');
            depDate = parts[0];
            retDate = parts[1];
        } else {
            depDate = dates;
        }

        // Get filter checks
        const allowedStops = [];
        if ($('#stopDirect').is(':checked')) allowedStops.push(0);
        if ($('#stop1').is(':checked')) allowedStops.push(1);
        if ($('#stop2').is(':checked')) allowedStops.push(2, 3, 4, 5); // 2+

        const request = {
            originLocationCode: origin,
            destinationLocationCode: destination,
            departureDate: depDate,
            returnDate: retDate,
            adults: adults,
            max: 30,
            sortBy: currentFlightSort
        };

        $('#flightListContainer').html('<div class="text-center my-5"><div class="spinner-border text-primary" role="status"><span class="visually-hidden">Loading...</span></div><p class="mt-2 text-muted">Searching for flights via Amadeus...</p></div>');

        $.ajax({
            url: '/api/flight/search',
            type: 'POST',
            contentType: 'application/json',
            data: JSON.stringify(request),
            success: function (response) {
                // Client side filtering for Stops
                let filteredItems = response.items;
                if (allowedStops.length > 0 && allowedStops.length < 3) {
                    filteredItems = filteredItems.filter(f => allowedStops.includes(f.stops));
                }
                response.items = filteredItems;
                response.totalItems = filteredItems.length;

                renderFlights(response);
            },
            error: function (error) {
                console.error("Error fetching flights", error);
                $('#flightListContainer').html('<div class="alert alert-danger">Error fetching flight results. Please check your locations and try again.</div>');
            }
        });
    }

    function formatCurrency(amount) {
        return new Intl.NumberFormat('vi-VN', { style: 'currency', currency: 'VND' }).format(amount * 1000);
    }

    function formatTime(dateTimeStr) {
        if (!dateTimeStr) return "";
        const d = new Date(dateTimeStr);
        return d.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});
    }

    function formatDuration(ptStr) {
        // PT2H30M -> 2h 30m
        if (!ptStr) return "";
        let str = ptStr.replace('PT', '').toLowerCase();
        return str;
    }

    function renderFlights(result) {
        $('#flightResultCount').text(`${result.totalItems} flights found`);

        const container = $('#flightListContainer');
        container.empty();

        if (result.items.length === 0) {
            container.html('<div class="alert alert-warning text-center my-5">No flights found matching your criteria.</div>');
            return;
        }

        let html = '';
        result.items.forEach(flight => {
            const stopsText = flight.stops === 0 ? "Bay thẳng" : (flight.stops === 1 ? "1 điểm dừng" : `${flight.stops} điểm dừng`);
            const stopsColor = flight.stops === 0 ? "text-success" : "text-danger";

            let returnHtml = '';
            if (flight.returnFlight) {
                const retStopsText = flight.returnFlight.stops === 0 ? "Bay thẳng" : (flight.returnFlight.stops === 1 ? "1 điểm dừng" : `${flight.returnFlight.stops} điểm dừng`);
                const retStopsColor = flight.returnFlight.stops === 0 ? "text-success" : "text-danger";

                returnHtml = `
                    <div class="d-flex align-items-center mt-4 pt-4 border-top">
                        <div class="flex-shrink-0 text-center" style="width: 80px;">
                            <img src="${flight.airlineLogoUrl}" class="img-fluid mb-1" style="max-height: 30px; object-fit: contain;">
                            <div class="small text-muted" style="font-size: 0.75rem;">${flight.airlineName}</div>
                        </div>
                        <div class="flex-grow-1 ms-4">
                            <div class="row align-items-center">
                                <div class="col-4 text-end">
                                    <div class="fs-5 fw-bold text-dark">${formatTime(flight.returnFlight.departureTime)}</div>
                                    <div class="text-muted small">${flight.returnFlight.departureCode}</div>
                                </div>
                                <div class="col-4 text-center px-0">
                                    <div class="text-muted small mb-2">${formatDuration(flight.returnFlight.duration)}</div>
                                    <div class="position-relative d-flex align-items-center justify-content-between px-2">
                                        <div style="width: 6px; height: 6px; border: 1px solid #6c757d; border-radius: 50%; background: white; z-index: 2;"></div>
                                        <div style="position: absolute; left: 10px; right: 10px; height: 1px; background-color: #6c757d; z-index: 1;"></div>
                                        <i class="bi bi-airplane-fill position-absolute text-muted bg-white px-1" style="left: 50%; transform: translateX(-50%) rotate(270deg); z-index: 3; font-size: 0.85rem;"></i>
                                        <div style="width: 6px; height: 6px; border: 1px solid #6c757d; border-radius: 50%; background: white; z-index: 2;"></div>
                                    </div>
                                    <div class="small mt-2 ${retStopsColor}">${retStopsText}</div>
                                </div>
                                <div class="col-4 text-start">
                                    <div class="fs-5 fw-bold text-dark">${formatTime(flight.returnFlight.arrivalTime)}</div>
                                    <div class="text-muted small">${flight.returnFlight.arrivalCode}</div>
                                </div>
                            </div>
                        </div>
                    </div>
                `;
            }

            html += `
                <div class="card mb-3 shadow-sm border flight-card-anim" style="border-radius: 8px;">
                    <div class="card-body p-0">
                        <div class="row g-0 align-items-center">
                            <div class="col-md-9 p-4">
                                <div class="d-flex align-items-center">
                                    <div class="flex-shrink-0 text-center" style="width: 80px;">
                                        <img src="${flight.airlineLogoUrl}" class="img-fluid mb-1" style="max-height: 30px; object-fit: contain;">
                                        <div class="small text-muted" style="font-size: 0.75rem;">${flight.airlineName}</div>
                                    </div>
                                    <div class="flex-grow-1 ms-4">
                                        <div class="row align-items-center">
                                            <div class="col-4 text-end">
                                                <div class="fs-5 fw-bold text-dark">${formatTime(flight.departureTime)}</div>
                                                <div class="text-muted small">${flight.departureCode}</div>
                                            </div>
                                            <div class="col-4 text-center px-0">
                                                <div class="text-muted small mb-2">${formatDuration(flight.duration)}</div>
                                                <div class="position-relative d-flex align-items-center justify-content-between px-2">
                                                    <div style="width: 6px; height: 6px; border: 1px solid #6c757d; border-radius: 50%; background: white; z-index: 2;"></div>
                                                    <div style="position: absolute; left: 10px; right: 10px; height: 1px; background-color: #6c757d; z-index: 1;"></div>
                                                    <i class="bi bi-airplane-fill position-absolute text-muted bg-white px-1" style="left: 50%; transform: translateX(-50%); z-index: 3; font-size: 0.85rem;"></i>
                                                    <div style="width: 6px; height: 6px; border: 1px solid #6c757d; border-radius: 50%; background: white; z-index: 2;"></div>
                                                </div>
                                                <div class="small mt-2 ${stopsColor}">${stopsText}</div>
                                            </div>
                                            <div class="col-4 text-start">
                                                <div class="fs-5 fw-bold text-dark">${formatTime(flight.arrivalTime)}</div>
                                                <div class="text-muted small">${flight.arrivalCode}</div>
                                            </div>
                                        </div>
                                    </div>
                                </div>

                                ${returnHtml}
                            </div>
                            
                            <div class="col-md-3 border-start text-end d-flex flex-column justify-content-center h-100 p-4" style="background-color: #fbfbfb; border-radius: 0 8px 8px 0;">
                                <div class="text-muted small mb-1">Tổng giá vé</div>
                                <div class="fs-4 fw-bold mb-1" style="color: #003580;">${formatCurrency(flight.totalPrice)}</div>
                                <div class="small text-muted mb-3" style="font-size: 0.75rem;">Bao gồm thuế và phí</div>
                                <button class="btn fw-bold w-100 text-white" style="background-color: #0071c2; padding: 10px 16px;">Xem chuyến bay <i class="bi bi-chevron-right ms-1"></i></button>
                            </div>
                        </div>
                    </div>
                </div>
            `;
        });

        container.html(html);
    }

    // Event Listeners
    $('#flightSearchForm').on('submit', function(e) {
        e.preventDefault();
        fetchFlights();
    });

    $('.flight-filter').on('change', function() {
        fetchFlights();
    });

    // Sort By Dropdown
    $(document).on('click', '#flightSortMenu .dropdown-item', function (e) {
        e.preventDefault();
        const sortVal = $(this).data('sort');
        const sortLabel = $(this).text();

        // Update active state
        $('#flightSortMenu .dropdown-item').removeClass('active');
        $(this).addClass('active');

        // Update button label
        $('#flightSortLabel').text(sortLabel);

        // Update sort state and re-fetch
        currentFlightSort = sortVal;
        fetchFlights();
    });

    // Add CSS rule dynamically for hover effect
    if (!$('#flightCardStyle').length) {
        $('<style>')
            .attr('id', 'flightCardStyle')
            .html(`
            .flight-card-anim { transition: box-shadow 0.2s, border-color 0.2s; border: 1px solid #e7e7e7; }
            .flight-card-anim:hover { box-shadow: 0 4px 12px rgba(0,0,0,.15)!important; border-color: #0071c2 !important; cursor: pointer; }
            .flight-card-anim .btn { transition: background-color 0.2s; }
            .flight-card-anim:hover .btn { background-color: #005a9e !important; }
        `)
            .appendTo('head');
    }

    // Initial load
    fetchFlights();
});
