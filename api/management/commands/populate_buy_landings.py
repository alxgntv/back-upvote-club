from django.core.management.base import BaseCommand
from api.models import BuyLanding
from decimal import Decimal


class Command(BaseCommand):
    help = 'Populate BuyLanding objects with SSR data'

    # Price configuration per action type (in points)
    PRICES = {
        'LIKE': Decimal('0.45'),
        'FOLLOW': Decimal('1.50'),
        'REPOST': Decimal('0.80'),
        'SAVE': Decimal('0.60'),
        'COMMENT': Decimal('2.00'),
        'UPVOTE': Decimal('2.00'),
        'DOWNVOTE': Decimal('2.00'),
        'UP': Decimal('2.00'),
        'DOWN': Decimal('2.00'),
        'STAR': Decimal('1.20'),
        'SUBSCRIBE': Decimal('2.50'),
        'CONNECT': Decimal('1.80'),
        'SHARE': Decimal('0.70'),
        'CLAP': Decimal('0.50'),
        'RESTACK': Decimal('0.90'),
        'BOOST': Decimal('3.00'),
        'FAVORITE': Decimal('0.55'),
        'INSTALL': Decimal('5.00'),
        'UNICORN': Decimal('1.50'),
        'REPLY': Decimal('2.20'),
        'REVIEW': Decimal('4.00'),
    }

    # Quantity steps per action type
    QUANTITY_STEPS = {
        'LIKE': [5, 10, 25, 50, 100, 250],
        'FOLLOW': [2, 5, 10, 20, 50, 100],
        'REPOST': [2, 5, 10, 25, 50, 100],
        'SAVE': [5, 10, 25, 50, 100, 250],
        'COMMENT': [2, 5, 10, 20, 30],
        'UPVOTE': [2, 5, 10, 20, 50, 100],
        'DOWNVOTE': [2, 5, 10, 20, 50],
        'UP': [2, 5, 10, 20, 50, 100],
        'DOWN': [2, 5, 10, 20, 50],
        'STAR': [5, 10, 25, 50, 100, 250],
        'SUBSCRIBE': [2, 5, 10, 20, 50, 100],
        'CONNECT': [2, 5, 10, 20, 50, 100],
        'SHARE': [5, 10, 25, 50, 100, 250],
        'CLAP': [5, 10, 25, 50, 100, 250],
        'RESTACK': [2, 5, 10, 25, 50, 100],
        'BOOST': [2, 5, 10, 20, 50],
        'FAVORITE': [5, 10, 25, 50, 100, 250],
        'INSTALL': [2, 5, 10, 20, 50],
        'UNICORN': [2, 5, 10, 25, 50, 100],
        'REPLY': [2, 5, 10, 20, 30],
        'REVIEW': [2, 5, 10, 20],
    }

    DEFAULT_QUANTITY_STEPS = [2, 5, 10, 20, 50, 100]

    # How It Works content
    HOW_IT_WORKS = [
        {
            "emoji": "🧗‍♂️",
            "title": "Real people, genuine engagement",
            "text": "We are a community-driven platform where real people support each other's growth through authentic interactions."
        },
        {
            "emoji": "👥",
            "title": "Trusted community since 2020",
            "text": "We maintain a safe and clean environment where community members exchange real engagement from verified accounts."
        },
        {
            "emoji": "🤖",
            "title": "Strict anti-bot protection",
            "text": "We actively block all bot-like accounts to ensure authentic engagement quality."
        },
        {
            "emoji": "🌐",
            "title": "Global community, diverse interests",
            "text": "Our worldwide network includes users from various niches and industries, ensuring relevant engagement for your content."
        },
        {
            "emoji": "🛡️",
            "title": "Safe & Secure",
            "text": "No passwords required — no risk to account integrity"
        }
    ]

    # FAQ content per social network
    FAQ_TEMPLATES = {
        'TWITTER': [
            {
                "q": "How long does delivery take?",
                "a": "Delivery typically takes 1-24 hours depending on the quantity ordered. Smaller orders complete faster, while larger orders may take up to 24 hours."
            },
            {
                "q": "Is it safe for my Twitter account?",
                "a": "Yes, absolutely safe. We use real community members with verified Twitter accounts. No bots, no passwords required."
            },
            {
                "q": "Will the engagement look natural?",
                "a": "Yes! All engagement comes from real people in our community, making it completely organic and natural."
            },
            {
                "q": "Can I get a refund?",
                "a": "Yes, we offer refunds if the service doesn't meet your expectations or if we can't deliver within the promised timeframe."
            },
            {
                "q": "Do I need to provide my password?",
                "a": "No, never! We only need the public URL to your post. We never ask for passwords or login credentials."
            }
        ],
        'REDDIT': [
            {
                "q": "How quickly will I receive Reddit upvotes?",
                "a": "Most orders are completed within 2-12 hours. The speed depends on your order size and current community availability."
            },
            {
                "q": "Will Reddit detect this as spam?",
                "a": "No, all upvotes come from real Reddit users with aged accounts and genuine activity history. It's completely safe."
            },
            {
                "q": "Can I target specific subreddits?",
                "a": "Yes, our community members participate in various subreddits. Just provide the post URL and we'll handle the rest."
            },
            {
                "q": "What if my post gets downvoted?",
                "a": "We only provide upvotes from real users. Natural Reddit activity may include some downvotes, but our service focuses on positive engagement."
            }
        ],
        'PRODUCTHUNT': [
            {
                "q": "How does ProductHunt upvoting work?",
                "a": "Our community members with verified ProductHunt accounts will upvote your product. All votes are from real users."
            },
            {
                "q": "Can this help me get to #1 Product of the Day?",
                "a": "While we provide real upvotes, ProductHunt ranking depends on many factors. Our service gives you a strong foundation and initial momentum."
            },
            {
                "q": "Is it against ProductHunt rules?",
                "a": "We provide real engagement from genuine users. Our community members discover and support products they find interesting."
            },
            {
                "q": "How long does delivery take?",
                "a": "Delivery is typically completed within 4-12 hours, but we recommend ordering early on launch day for best results."
            }
        ],
        'DEFAULT': [
            {
                "q": "How long does delivery take?",
                "a": "Delivery typically takes 1-24 hours depending on quantity and platform. Smaller orders usually complete within a few hours."
            },
            {
                "q": "Is this safe for my account?",
                "a": "Yes, completely safe. We use only real community members with verified accounts. No bots, no passwords required."
            },
            {
                "q": "Can I get a refund?",
                "a": "Yes, we offer refunds if we can't deliver the service as promised or if you're not satisfied with the results."
            },
            {
                "q": "Do you need my password?",
                "a": "Never! We only need the public URL to your content. We never ask for passwords or private information."
            }
        ]
    }

    def get_faq_for_network(self, network_code):
        """Get FAQ specific to social network"""
        return self.FAQ_TEMPLATES.get(network_code, self.FAQ_TEMPLATES['DEFAULT'])

    def generate_meta_data(self, landing):
        """Generate SEO meta data for landing"""
        network_name = landing.social_network.name
        action_name = landing.action.name_plural or landing.action.name
        action_singular = landing.action.name
        
        meta_title = f"Buy {network_name} {action_name} - Real & Instant Delivery | Upvote Club"
        meta_description = f"Get real {network_name} {action_name.lower()} from verified accounts. Safe, fast delivery. Trusted since 2020. No bots, real people only. Start from $0.50 per {action_singular.lower()}."
        og_title = f"Buy Real {network_name} {action_name}"
        og_description = f"Boost your {network_name} presence with real {action_name.lower()} from our trusted community. Fast delivery, verified accounts, no bots."
        
        return meta_title, meta_description, og_title, og_description

    def handle(self, *args, **options):
        """Main handler for the command"""
        landings = BuyLanding.objects.all()
        
        self.stdout.write(self.style.SUCCESS('\n' + '='*60))
        self.stdout.write(self.style.SUCCESS(f'Found {landings.count()} Buy Landing(s) to populate'))
        self.stdout.write(self.style.SUCCESS('='*60 + '\n'))
        
        updated_count = 0
        
        for landing in landings:
            network_code = landing.social_network.code
            action_code = landing.action.code
            network_name = landing.social_network.name
            action_name = landing.action.name_plural or landing.action.name
            
            self.stdout.write(f"\nProcessing: {network_name} {action_name} ({landing.slug})")
            
            # Set price per action
            price = self.PRICES.get(action_code, Decimal('2.00'))
            landing.price_per_action = price
            self.stdout.write(self.style.SUCCESS(f"  ✓ Price per action: {price} points"))
            
            # Set quantity steps
            steps = self.QUANTITY_STEPS.get(action_code, self.DEFAULT_QUANTITY_STEPS)
            landing.quantity_steps = steps
            self.stdout.write(self.style.SUCCESS(f"  ✓ Quantity steps: {steps}"))
            
            # Set How It Works
            landing.how_it_works_title = "How It Works?"
            landing.how_it_works = self.HOW_IT_WORKS
            self.stdout.write(self.style.SUCCESS(f"  ✓ How It Works: {len(self.HOW_IT_WORKS)} items"))
            
            # Set FAQ
            faq = self.get_faq_for_network(network_code)
            landing.faq_section_title = "Frequently Asked Questions"
            landing.faq = faq
            self.stdout.write(self.style.SUCCESS(f"  ✓ FAQ: {len(faq)} questions"))
            
            # Set Reviews section title
            landing.reviews_section_title = "What Our Customers Say"
            self.stdout.write(self.style.SUCCESS(f"  ✓ Reviews section title set"))
            
            # Generate and set meta data
            meta_title, meta_description, og_title, og_description = self.generate_meta_data(landing)
            landing.meta_title = meta_title
            landing.meta_description = meta_description
            landing.og_title = og_title
            landing.og_description = og_description
            self.stdout.write(self.style.SUCCESS(f"  ✓ SEO meta data generated"))
            
            # Save the landing
            landing.save()
            updated_count += 1
            self.stdout.write(self.style.SUCCESS(f"  ✅ Saved successfully!"))
        
        self.stdout.write(self.style.SUCCESS('\n' + '='*60))
        self.stdout.write(self.style.SUCCESS(f'✅ Successfully updated {updated_count} Buy Landing(s)!'))
        self.stdout.write(self.style.SUCCESS('='*60 + '\n'))
