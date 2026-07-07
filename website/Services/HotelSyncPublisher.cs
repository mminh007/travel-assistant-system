using System.Text;
using System.Text.Json;
using RabbitMQ.Client;
using Booking.Web.Models.Domain;

namespace Booking.Web.Services
{
    public class HotelSyncPublisher : IDisposable
    {
        private readonly IConnection _connection;
        private readonly IModel _channel;
        private const string QueueName = "hotel_sync_queue";

        public HotelSyncPublisher(IConfiguration configuration)
        {
            var factory = new ConnectionFactory
            {
                Uri = new Uri(configuration["RabbitMQ:Url"] ?? "amqp://guest:guest@localhost:5672/")
            };
            
            try 
            {
                _connection = factory.CreateConnection();
                _channel = _connection.CreateModel();

                // Ensure queue exists with the same config as Python consumer
                _channel.QueueDeclare(
                    queue: QueueName,
                    durable: true,
                    exclusive: false,
                    autoDelete: false,
                    arguments: new Dictionary<string, object>
                    {
                        { "x-dead-letter-exchange", "dlx_hotel_exchange" },
                        { "x-dead-letter-routing-key", "hotel_sync_dlq" }
                    }
                );
            }
            catch (Exception ex)
            {
                // In a real production scenario, we should log this and perhaps not crash the app 
                // if RabbitMQ is temporarily down during startup.
                Console.WriteLine($"[Warning] Failed to connect to RabbitMQ during startup: {ex.Message}");
            }
        }

        public void PublishHotelEvent(string actionType, Hotel hotel)
        {
            if (_channel == null || _channel.IsClosed)
            {
                Console.WriteLine("[Warning] RabbitMQ channel is not open. Skipping hotel event publish.");
                return;
            }

            var roomTypes = hotel.RoomTypes?.Select(rt => (object)new
            {
                name = rt.Name,
                type = rt.Type,
                price_per_night = rt.PricePerNight,
                max_occupancy = rt.MaxOccupancy,
                amenities = TryParseJson(rt.Amenities)
            }).ToList() ?? new List<object>();

            var payload = new
            {
                action_type = actionType,   // "Create" | "Update" | "Delete"
                hotel_id = hotel.Id.ToString(),
                data = new
                {
                    name = hotel.Name,
                    description = hotel.Description,
                    address = hotel.Address,
                    city = hotel.City,
                    country = hotel.Country,
                    star_rating = hotel.StarRating,
                    latitude = hotel.Latitude,
                    longitude = hotel.Longitude,
                    amenities = TryParseJson(hotel.Amenities),
                    room_types = roomTypes
                }
            };

            var body = Encoding.UTF8.GetBytes(JsonSerializer.Serialize(payload));
            var props = _channel.CreateBasicProperties();
            props.Persistent = true;   // Ensure message isn't lost on restart

            _channel.BasicPublish(
                exchange: "",           // Default exchange -> route by queue name
                routingKey: QueueName,
                basicProperties: props,
                body: body
            );
            
            Console.WriteLine($"[Info] Published {actionType} event for hotel {hotel.Id}");
        }

        private static List<string> TryParseJson(string json)
        {
            if (string.IsNullOrWhiteSpace(json)) return new List<string>();
            try 
            { 
                return JsonSerializer.Deserialize<List<string>>(json) ?? new List<string>(); 
            }
            catch 
            { 
                return new List<string>(); 
            }
        }

        public void Dispose()
        {
            _channel?.Close();
            _connection?.Close();
        }
    }
}
