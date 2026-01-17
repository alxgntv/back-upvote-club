from django.core.management.base import BaseCommand
from api.models import BuyLanding
from decimal import Decimal


class Command(BaseCommand):
    help = 'Populate BuyLanding objects with SSR data'

    # Price configuration per action type (in points)
    # 
    # Pricing structure:
    # - LIKE: $0.45 for all social networks
    # - UPVOTE (except ProductHunt): $0.90
    # - FOLLOW: $0.90 for all social networks
    # - COMMENT: $0.90 for all social networks
    # - SAVE: $0.90 for all social networks
    # - REPOST: $0.90 for all social networks
    # - All other actions: $0.90
    #
    PRICES = {
        # Likes - $0.45 для всех соц.сетей
        'LIKE': Decimal('0.45'),
        
        # Followers - $0.90 для всех
        'FOLLOW': Decimal('0.90'),
        
        # Upvotes - $0.90 для всех кроме ProductHunt (ProductHunt отдельно)
        'UPVOTE': Decimal('0.90'),
        'UP': Decimal('0.90'),
        'DOWN': Decimal('0.90'),
        'DOWNVOTE': Decimal('0.90'),
        
        # Comments - $0.90 для всех
        'COMMENT': Decimal('0.90'),
        'REPLY': Decimal('0.90'),
        
        # Saves - $0.90 для всех
        'SAVE': Decimal('0.90'),
        
        # Reposts - $0.90 для всех
        'REPOST': Decimal('0.90'),
        'RESTACK': Decimal('0.90'),
        'BOOST': Decimal('0.90'),
        'SHARE': Decimal('0.90'),
        
        # Stars & Favorites - $0.90
        'STAR': Decimal('0.90'),
        'FAVORITE': Decimal('0.90'),
        
        # Claps - $0.90
        'CLAP': Decimal('0.90'),
        
        # Connections - $0.90
        'CONNECT': Decimal('0.90'),
        
        # Unicorns - $0.90
        'UNICORN': Decimal('0.90'),
        
        # Watch - $0.90
        'WATCH': Decimal('0.90'),
        
        # Installs & Reviews - $0.90
        'INSTALL': Decimal('0.90'),
        'REVIEW': Decimal('0.90'),
    }

    # Quantity steps per action type
    # Единый шаг для всех действий: 2, 3, 4, 5, 6, 8, 10
    QUANTITY_STEPS = {
        'LIKE': [2, 3, 4, 5, 6, 8, 10],
        'FOLLOW': [2, 3, 4, 5, 6, 8, 10],
        'REPOST': [2, 3, 4, 5, 6, 8, 10],
        'SAVE': [2, 3, 4, 5, 6, 8, 10],
        'COMMENT': [2, 3, 4, 5, 6, 8, 10],
        'UPVOTE': [2, 3, 4, 5, 6, 8, 10],
        'DOWNVOTE': [2, 3, 4, 5, 6, 8, 10],
        'UP': [2, 3, 4, 5, 6, 8, 10],
        'DOWN': [2, 3, 4, 5, 6, 8, 10],
        'STAR': [2, 3, 4, 5, 6, 8, 10],
        'CONNECT': [2, 3, 4, 5, 6, 8, 10],
        'SHARE': [2, 3, 4, 5, 6, 8, 10],
        'CLAP': [2, 3, 4, 5, 6, 8, 10],
        'RESTACK': [2, 3, 4, 5, 6, 8, 10],
        'BOOST': [2, 3, 4, 5, 6, 8, 10],
        'FAVORITE': [2, 3, 4, 5, 6, 8, 10],
        'INSTALL': [2, 3, 4, 5, 6, 8, 10],
        'UNICORN': [2, 3, 4, 5, 6, 8, 10],
        'REPLY': [2, 3, 4, 5, 6, 8, 10],
        'REVIEW': [2, 3, 4, 5, 6, 8, 10],
        'WATCH': [2, 3, 4, 5, 6, 8, 10],
    }

    DEFAULT_QUANTITY_STEPS = [2, 3, 4, 5, 6, 8, 10]

    # How It Works content (will be customized per landing)
    HOW_IT_WORKS = [
        {
            "emoji": "🔢",
            "title": "Choose Your Quantity",
            "text": "Pick how many items you want for your content. Select any amount that fits your goals."
        },
        {
            "emoji": "✉️",
            "title": "Quick Sign Up",
            "text": "Create an account using Email or Google in seconds. We never ask for social network passwords or logins."
        },
        {
            "emoji": "💳",
            "title": "Secure Payment",
            "text": "Pay safely for your order. All transactions are encrypted for your peace of mind."
        },
        {
            "emoji": "📝",
            "title": "Task Created Instantly",
            "text": "Right after payment, your task goes live for the community to complete. Just submit your public post or profile link."
        },
        {
            "emoji": "🕒",
            "title": "Community Delivers in 24 Hours",
            "text": "Real people complete your actions—usually within 1-24 hours. No bots. No automation."
        },
        {
            "emoji": "🚀",
            "title": "Unlimited Growth Campaigns",
            "text": "Founders and creators can launch unlimited tasks. Run as many engagement campaigns as you need."
        },
        {
            "emoji": "🌟",
            "title": "Golden Hour Growth Technique",
            "text": "For maximum impact, boost your post right after publishing with about 20 likes, 20 comments, 20 saves, and 20 reposts. This early activity can significantly increase your post's visibility and often leads to better results."
        }
    ]

    # FAQ content (universal for all networks)
    FAQ_TEMPLATES = [
        {
            "q": "What makes Upvote Club different from typical 'buy engagement' sites?",
            "a": "Upvote Club is a community-powered platform. Actions come only from real people—not bots or automation. We focus on transparency, non-drop engagement, and strict moderation for quality."
        },
        {
            "q": "How does Upvote Club work?",
            "a": "You create a task requesting actions. Community members complete your task to earn points. Everyone helps each other grow in a real way."
        },
        {
            "q": "Is it safe to buy engagement here?",
            "a": "Our system is designed to be safe by using only real users and never asking for social network logins. We have strong moderation to reduce risk."
        },
        {
            "q": "Do I need to give my password?",
            "a": "Never. Upvote Club will never ask for any social network password or login. You just provide a public link to your content."
        },
        {
            "q": "How quickly will I receive my order?",
            "a": "Most tasks start soon after payment and typically complete within 1-24 hours, depending on the quantity."
        },
        {
            "q": "Is my information confidential?",
            "a": "Yes. Only your public link is visible to members who complete your task. Your account info and order remain private."
        },
        {
            "q": "What is non-drop engagement?",
            "a": "It means the actions come from real people and are unlikely to disappear later, unlike fake engagement from bots."
        },
        {
            "q": "Who completes the actions on my posts?",
            "a": "Actions are completed by real members of the Upvote Club community who earn points for helping others."
        },
        {
            "q": "What moderation do you have?",
            "a": "We review all activity. Bot-like or suspicious accounts are blocked. We focus on quality engagement and a trustworthy experience."
        },
        {
            "q": "How do points and tasks work?",
            "a": "You spend points to request actions. Community members earn points by completing tasks. This keeps engagement authentic and fair."
        },
        {
            "q": "Can I see exactly who did each action?",
            "a": "For privacy, we do not share user identities. You will see real engagement show up on your content."
        },
        {
            "q": "What should I do if I have an issue with my order?",
            "a": "Contact our support team. We'll review your case and work together on a fair solution."
        },
        {
            "q": "Do you support actions like reposts or saves?",
            "a": "Yes! You can create tasks for likes, comments, reposts, saves, followers, and more."
        },
        {
            "q": "What's the best growth tactic for early exposure?",
            "a": "Use the Golden Hour Growth Technique—right after your post goes live, boost it with ~20 likes, 20 comments, 20 saves, and 20 reposts to increase early momentum."
        },
        {
            "q": "How do I scale my social network growth on Upvote Club?",
            "a": "There's no limit. Founders, indie makers, and marketers can create unlimited campaigns to drive growth."
        },
        {
            "q": "Will Upvote Club's engagement look natural on my content?",
            "a": "Yes. Since all actions are from real people with unique profiles, it blends in naturally with organic activity."
        },
        {
            "q": "Is using Upvote Club risky for my account?",
            "a": "Engagement comes from real users, not automation. No online service is risk-free, but our human-first approach is designed to minimize issues."
        },
        {
            "q": "What ICP (ideal customer) is Upvote Club designed for?",
            "a": "Upvote Club serves founders, indie makers, marketers, engineers, designers, and small business owners focused on real growth."
        },
        {
            "q": "Are refunds available?",
            "a": "If there's a problem, reach out to support first. We'll investigate and help resolve any concerns."
        },
        {
            "q": "How soon can I create another campaign?",
            "a": "Whenever you want. Upvote Club allows you to run multiple tasks or campaigns at the same time—no limits."
        },
        {
            "q": "What keywords can I use to find your service?",
            "a": "You can search: buy engagement, real social growth, Upvote Club, non-drop engagement services."
        },
        {
            "q": "Can I combine different actions for stronger impact?",
            "a": "Definitely. Mix likes, comments, reposts, and saves in one campaign for a higher visibility boost."
        }
    ]

    def generate_meta_data(self, landing):
        """
        Generate SEO meta data for landing.
        Facts: Upvote Club is a community-powered engagement exchange platform.
        It helps users grow on social networks by receiving actions from REAL people (not bots).
        """
        network_name = landing.social_network.name
        action_name = landing.action.name_plural or landing.action.name
        action_singular = landing.action.name

        meta_title = f"Buy {network_name} {action_name} From Real People | Instant Delivery – Upvote Club"
        meta_description = (
            f"Grow on {network_name} with authentic {action_name.lower()} delivered by real, verified users — never bots. "
            f"Upvote Club is a community-powered engagement exchange platform: safe, fast, and trusted. Start from $0.45 per {action_singular.lower()}."
        )
        og_title = f"Buy Real {network_name} {action_name} – Community Engagement | Upvote Club"
        og_description = (
            f"Boost your {network_name} presence with genuine {action_name.lower()} from real community members. "
            "Upvote Club connects you with actual people for safe, organic social growth — zero bots or fakes. Instant delivery."
        )

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
            price = self.PRICES.get(action_code, Decimal('0.90'))
            landing.price_per_action = price
            self.stdout.write(self.style.SUCCESS(f"  ✓ Price per action: ${price}"))
            
            # Set quantity steps
            steps = self.QUANTITY_STEPS.get(action_code, self.DEFAULT_QUANTITY_STEPS)
            landing.quantity_steps = steps
            self.stdout.write(self.style.SUCCESS(f"  ✓ Quantity steps: {steps}"))
            
            # Set How It Works
            landing.how_it_works_title = "How It Works?"
            landing.how_it_works = self.HOW_IT_WORKS
            self.stdout.write(self.style.SUCCESS(f"  ✓ How It Works: {len(self.HOW_IT_WORKS)} items"))
            
            # Set FAQ
            landing.faq_section_title = "Frequently Asked Questions"
            landing.faq = self.FAQ_TEMPLATES
            self.stdout.write(self.style.SUCCESS(f"  ✓ FAQ: {len(self.FAQ_TEMPLATES)} questions"))
            
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
