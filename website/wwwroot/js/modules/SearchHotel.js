$(document).ready(function () {

    function fetchHotels(page = 1) {
        // 1. Gather Search Bar Data
        const destination = $('input[name="destination"]').val() || '';
        const dates = $('#dateRangePicker').val() || '';
        let checkIn = null;
        let checkOut = null;
        
        if (dates.includes(' to ')) {
            const parts = dates.split(' to ');
            checkIn = parts[0];
            checkOut = parts[1];
        }

        const adults = parseInt($('#adultCount').text()) || 2;
        const children = parseInt($('#childCount').text()) || 0;
        const rooms = parseInt($('#roomCount').text()) || 1;

        // 2. Gather Filter Sidebar Data
        const propertyTypes = [];
        if ($('#typeHotel').is(':checked')) propertyTypes.push('Hotel');
        if ($('#typeApartment').is(':checked')) propertyTypes.push('Apartment');
        if ($('#typeResort').is(':checked')) propertyTypes.push('Resort');

        // Budget logic (simple mapping for demonstration)
        let minPrice = null;
        let maxPrice = null;
        if ($('#budget1').is(':checked')) { maxPrice = 1000000; }
        if ($('#budget2').is(':checked')) { 
            if (minPrice === null || minPrice > 1000000) minPrice = 1000000;
            if (maxPrice === null || maxPrice < 2000000) maxPrice = 2000000;
        }
        if ($('#budget3').is(':checked')) {
            if (minPrice === null || minPrice > 2000000) minPrice = 2000000;
            maxPrice = null; // 2m+ has no upper bound
        }

        // 3. Build Request Object
        const request = {
            destination: destination,
            checkIn: checkIn,
            checkOut: checkOut,
            adults: adults,
            children: children,
            rooms: rooms,
            propertyTypes: propertyTypes.length > 0 ? propertyTypes : null,
            minPrice: minPrice,
            maxPrice: maxPrice,
            page: page,
            pageSize: 10
        };

        // 4. Show loading state
        $('#hotelListContainer').html('<div class="text-center my-5"><div class="spinner-border text-primary" role="status"><span class="visually-hidden">Loading...</span></div><p class="mt-2 text-muted">Searching for best properties...</p></div>');

        // 5. Call API
        $.ajax({
            url: '/api/hotel/search',
            type: 'POST',
            contentType: 'application/json',
            data: JSON.stringify(request),
            success: function (response) {
                renderHotels(response);
            },
            error: function (error) {
                console.error("Error fetching hotels", error);
                $('#hotelListContainer').html('<div class="alert alert-danger">Error fetching results. Please try again.</div>');
            }
        });
    }

    function formatCurrency(amount) {
        return new Intl.NumberFormat('vi-VN', { style: 'currency', currency: 'VND' }).format(amount);
    }

    function renderHotels(result) {
        // Update header count
        const dest = $('input[name="destination"]').val() || 'Vietnam';
        $('h3').text(`${dest}: ${result.totalItems} properties found`);

        const container = $('#hotelListContainer');
        container.empty();

        if (result.items.length === 0) {
            container.html('<div class="alert alert-warning text-center my-5">No properties found matching your criteria. Try adjusting your filters.</div>');
            return;
        }

        // Build HTML for each hotel card
        let html = '';
        result.items.forEach(hotel => {
            // Generate star icons
            let stars = '';
            for (let i = 0; i < hotel.starRating; i++) {
                stars += '<i class="bi bi-star-fill text-warning small"></i> ';
            }

            // Generate amenities badges
            let amenitiesHtml = '';
            hotel.topAmenities.forEach(a => {
                amenitiesHtml += `<span class="badge bg-light text-dark border me-1 mb-1 fw-normal"><i class="bi bi-check text-success"></i> ${a}</span>`;
            });

            // Card Template (resembling HotelCardModule.cshtml)
            html += `
                <div class="card mb-3 shadow-sm border-0 position-relative hotel-card-anim">
                    <div class="row g-0">
                        <div class="col-md-4 position-relative">
                            <img src="${hotel.thumbnailUrl}" class="img-fluid rounded-start h-100 object-fit-cover" style="min-height: 240px;" alt="${hotel.name}">
                            <div class="position-absolute top-0 end-0 p-2">
                                <button class="btn btn-light btn-sm rounded-circle shadow-sm"><i class="bi bi-heart"></i></button>
                            </div>
                        </div>
                        <div class="col-md-8">
                            <div class="card-body d-flex flex-column h-100">
                                <div class="d-flex justify-content-between">
                                    <div class="w-75">
                                        <h5 class="card-title fw-bold text-primary mb-1">${hotel.name}</h5>
                                        <div class="mb-2">
                                            ${stars}
                                            <span class="ms-2 small text-primary bg-primary bg-opacity-10 px-2 py-1 rounded"><i class="bi bi-hand-thumbs-up-fill"></i> ${hotel.propertyTypes.join(', ')}</span>
                                        </div>
                                        <p class="card-text small mb-2">
                                            <a href="#" class="text-primary text-decoration-underline">${hotel.address}, ${hotel.city}</a>
                                            <span class="text-muted ms-2">Great location</span>
                                        </p>
                                        <div class="mb-2 d-flex flex-wrap gap-1">
                                            ${amenitiesHtml}
                                        </div>
                                    </div>
                                    <div class="text-end">
                                        <div class="d-flex align-items-center justify-content-end mb-2">
                                            <div class="me-2 text-end">
                                                <div class="fw-bold">Excellent</div>
                                                <div class="text-muted small">Reviews</div>
                                            </div>
                                            <div class="bg-primary text-white fw-bold rounded p-2 fs-5">8.9</div>
                                        </div>
                                    </div>
                                </div>

                                <div class="mt-auto row align-items-end">
                                    <div class="col-7">
                                        <div class="text-success small fw-bold mt-1"><i class="bi bi-check text-success"></i> Free cancellation</div>
                                        <div class="text-success small"><i class="bi bi-check text-success"></i> No prepayment needed <span class="text-muted">– pay at the property</span></div>
                                    </div>
                                    <div class="col-5 text-end d-flex flex-column justify-content-end">
                                        <div class="text-muted small mb-1">Price from (per night)</div>
                                        <div class="fs-4 fw-bold text-danger mb-2">${formatCurrency(hotel.minPricePerNight)}</div>
                                        <a href="#" class="btn btn-primary fw-bold w-100">See availability <i class="bi bi-chevron-right small"></i></a>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            `;
        });

        container.html(html);
        renderPagination(result);
    }

    function renderPagination(result) {
        const pagContainer = $('#paginationContainer');
        if (result.totalPages <= 1) {
            pagContainer.empty();
            return;
        }

        let html = '<ul class="pagination justify-content-center">';
        html += `<li class="page-item ${result.currentPage === 1 ? 'disabled' : ''}">
                    <a class="page-link pagination-btn" href="#" data-page="${result.currentPage - 1}">Previous</a>
                 </li>`;
                 
        for (let i = 1; i <= result.totalPages; i++) {
            html += `<li class="page-item ${result.currentPage === i ? 'active' : ''}">
                        <a class="page-link pagination-btn" href="#" data-page="${i}">${i}</a>
                     </li>`;
        }
        
        html += `<li class="page-item ${result.currentPage === result.totalPages ? 'disabled' : ''}">
                    <a class="page-link pagination-btn" href="#" data-page="${result.currentPage + 1}">Next</a>
                 </li>`;
        html += '</ul>';
        pagContainer.html(html);
    }

    // Event Listeners
    $('#searchForm').on('submit', function(e) {
        e.preventDefault();
        fetchHotels(1);
    });

    $('.form-check-input').on('change', function() {
        fetchHotels(1);
    });

    $(document).on('click', '.pagination-btn', function(e) {
        e.preventDefault();
        const page = $(this).data('page');
        if (page) {
            fetchHotels(page);
            window.scrollTo({ top: 0, behavior: 'smooth' });
        }
    });

    // Initial load
    fetchHotels(1);
});
