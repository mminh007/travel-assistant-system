using Booking.Web.Models.DTOs;
using Booking.Web.Services.Interfaces;
using Microsoft.Extensions.Configuration;
using System;
using System.Collections.Generic;
using System.Linq;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Text;
using System.Text.Json;
using System.Threading.Tasks;

namespace Booking.Web.Services
{
    public class AmadeusService : IAmadeusService
    {
        private readonly HttpClient _httpClient;
        private readonly IConfiguration _config;
        private string _accessToken = string.Empty;
        private DateTime _tokenExpiry = DateTime.MinValue;

        public AmadeusService(HttpClient httpClient, IConfiguration config)
        {
            _httpClient = httpClient;
            _config = config;
            _httpClient.BaseAddress = new Uri(_config["AmadeusApi:BaseUrl"] ?? "https://test.api.amadeus.com");
        }

        private async Task EnsureAccessTokenAsync()
        {
            if (DateTime.UtcNow < _tokenExpiry && !string.IsNullOrEmpty(_accessToken))
            {
                return; // Token still valid
            }

            var apiKey = _config["AmadeusApi:ApiKey"];
            var apiSecret = _config["AmadeusApi:ApiSecret"];

            if (apiKey == "YOUR_API_KEY") 
            {
                // Fake token for demo if no real keys provided
                _accessToken = "FAKE_TOKEN";
                _tokenExpiry = DateTime.UtcNow.AddHours(1);
                return;
            }

            var request = new HttpRequestMessage(HttpMethod.Post, "/v1/security/oauth2/token");
            request.Content = new StringContent($"grant_type=client_credentials&client_id={apiKey}&client_secret={apiSecret}", Encoding.UTF8, "application/x-www-form-urlencoded");

            var response = await _httpClient.SendAsync(request);
            response.EnsureSuccessStatusCode();

            var jsonString = await response.Content.ReadAsStringAsync();
            using var doc = JsonDocument.Parse(jsonString);
            
            _accessToken = doc.RootElement.GetProperty("access_token").GetString() ?? "";
            int expiresIn = doc.RootElement.GetProperty("expires_in").GetInt32();
            _tokenExpiry = DateTime.UtcNow.AddSeconds(expiresIn - 60); // 60s buffer
        }

        public async Task<List<FlightDto>> SearchFlightsAsync(SearchFlightRequest request)
        {
            await EnsureAccessTokenAsync();

            var resultList = new List<FlightDto>();

            // Mock response if no real API keys are provided
            if (_accessToken == "FAKE_TOKEN" || string.IsNullOrEmpty(_config["AmadeusApi:ApiKey"]) || _config["AmadeusApi:ApiKey"] == "YOUR_API_KEY")
            {
                return GenerateMockFlights(request);
            }

            _httpClient.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", _accessToken);

            // Construct query URL
            var url = $"/v2/shopping/flight-offers?originLocationCode={request.OriginLocationCode}&destinationLocationCode={request.DestinationLocationCode}&departureDate={request.DepartureDate}&adults={request.Adults}&max={request.Max}";
            
            if (!string.IsNullOrEmpty(request.ReturnDate))
            {
                url += $"&returnDate={request.ReturnDate}";
            }

            var response = await _httpClient.GetAsync(url);
            
            if (!response.IsSuccessStatusCode)
            {
                // In a real app, log the error and handle it gracefully
                var errorString = await response.Content.ReadAsStringAsync();
                Console.WriteLine($"Amadeus API Error: {errorString}");
                return resultList;
            }

            var jsonString = await response.Content.ReadAsStringAsync();
            using var doc = JsonDocument.Parse(jsonString);

            var dataElement = doc.RootElement.GetProperty("data");

            foreach (var offer in dataElement.EnumerateArray())
            {
                var priceEl = offer.GetProperty("price");
                var total = priceEl.GetProperty("total").GetString() ?? "0";
                var currency = priceEl.GetProperty("currency").GetString() ?? "USD";

                var itineraries = offer.GetProperty("itineraries").EnumerateArray().ToList();
                if (!itineraries.Any()) continue;

                var outItinerary = itineraries[0];
                var outSegments = outItinerary.GetProperty("segments").EnumerateArray().ToList();
                
                var firstSeg = outSegments.First();
                var lastSeg = outSegments.Last();
                
                var airlineCode = firstSeg.GetProperty("carrierCode").GetString() ?? "VN";

                var dto = new FlightDto
                {
                    Id = offer.GetProperty("id").GetString() ?? Guid.NewGuid().ToString(),
                    AirlineName = GetAirlineName(airlineCode),
                    AirlineLogoUrl = $"https://content.airhex.com/content/logos/airlines_{airlineCode}_200_200_s.png?md5apikey=F3B2G1",
                    DepartureTime = firstSeg.GetProperty("departure").GetProperty("at").GetString() ?? "",
                    ArrivalTime = lastSeg.GetProperty("arrival").GetProperty("at").GetString() ?? "",
                    Duration = outItinerary.GetProperty("duration").GetString() ?? "",
                    DepartureCode = firstSeg.GetProperty("departure").GetProperty("iataCode").GetString() ?? "",
                    ArrivalCode = lastSeg.GetProperty("arrival").GetProperty("iataCode").GetString() ?? "",
                    TotalPrice = total,
                    Currency = currency,
                    Stops = outSegments.Count - 1
                };

                // Round trip
                if (itineraries.Count > 1)
                {
                    var retItinerary = itineraries[1];
                    var retSegments = retItinerary.GetProperty("segments").EnumerateArray().ToList();
                    dto.ReturnFlight = new FlightRouteDto
                    {
                        DepartureTime = retSegments.First().GetProperty("departure").GetProperty("at").GetString() ?? "",
                        ArrivalTime = retSegments.Last().GetProperty("arrival").GetProperty("at").GetString() ?? "",
                        Duration = retItinerary.GetProperty("duration").GetString() ?? "",
                        DepartureCode = retSegments.First().GetProperty("departure").GetProperty("iataCode").GetString() ?? "",
                        ArrivalCode = retSegments.Last().GetProperty("arrival").GetProperty("iataCode").GetString() ?? "",
                        Stops = retSegments.Count - 1
                    };
                }

                resultList.Add(dto);
            }

            return resultList;
        }

        private string GetAirlineName(string code)
        {
            var dict = new Dictionary<string, string>
            {
                { "VN", "Vietnam Airlines" },
                { "VJ", "VietJet Air" },
                { "QH", "Bamboo Airways" },
                { "VU", "Vietravel Airlines" },
                { "BL", "Pacific Airlines" }
            };
            return dict.ContainsKey(code) ? dict[code] : code;
        }

        private List<FlightDto> GenerateMockFlights(SearchFlightRequest request)
        {
            var rand = new Random();
            var list = new List<FlightDto>();
            string[] airlines = { "VN", "VJ", "QH" };
            
            for (int i = 0; i < request.Max; i++)
            {
                var code = airlines[rand.Next(airlines.Length)];
                var depTime = DateTime.Parse(request.DepartureDate).AddHours(rand.Next(6, 20)).AddMinutes(rand.Next(0, 60));
                var arrTime = depTime.AddHours(rand.Next(1, 4)).AddMinutes(rand.Next(0, 60));
                
                var dto = new FlightDto
                {
                    Id = Guid.NewGuid().ToString(),
                    AirlineName = GetAirlineName(code),
                    AirlineLogoUrl = $"https://content.airhex.com/content/logos/airlines_{code}_200_200_s.png",
                    DepartureTime = depTime.ToString("yyyy-MM-ddTHH:mm:ss"),
                    ArrivalTime = arrTime.ToString("yyyy-MM-ddTHH:mm:ss"),
                    Duration = $"PT{(int)(arrTime - depTime).TotalHours}H{(arrTime - depTime).Minutes}M",
                    DepartureCode = request.OriginLocationCode,
                    ArrivalCode = request.DestinationLocationCode,
                    TotalPrice = rand.Next(800, 3000).ToString() + ".00",
                    Currency = "VND", // Represented in thousands
                    Stops = rand.Next(0, 2)
                };

                if (!string.IsNullOrEmpty(request.ReturnDate))
                {
                    var retDepTime = DateTime.Parse(request.ReturnDate).AddHours(rand.Next(6, 20)).AddMinutes(rand.Next(0, 60));
                    var retArrTime = retDepTime.AddHours(rand.Next(1, 4)).AddMinutes(rand.Next(0, 60));
                    
                    dto.ReturnFlight = new FlightRouteDto
                    {
                        DepartureTime = retDepTime.ToString("yyyy-MM-ddTHH:mm:ss"),
                        ArrivalTime = retArrTime.ToString("yyyy-MM-ddTHH:mm:ss"),
                        Duration = $"PT{(int)(retArrTime - retDepTime).TotalHours}H{(retArrTime - retDepTime).Minutes}M",
                        DepartureCode = request.DestinationLocationCode,
                        ArrivalCode = request.OriginLocationCode,
                        Stops = rand.Next(0, 2)
                    };
                    
                    dto.TotalPrice = (int.Parse(dto.TotalPrice.Split('.')[0]) * 2).ToString() + ".00";
                }

                list.Add(dto);
            }
            
            return list.OrderBy(f => double.Parse(f.TotalPrice)).ToList();
        }
    }
}
