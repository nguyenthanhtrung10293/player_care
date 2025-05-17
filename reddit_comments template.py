import praw
import re
import openai
import time
import pandas as pd

# Replace these with your Reddit app credentials
CLIENT_ID = 'YOUR CLIENT ID HERE'
CLIENT_SECRET = 'YOUR CLIENT SECRET'
USER_AGENT = 'YOUR USER AGENT HERE'
USERNAME = ''  # Add your Reddit username
PASSWORD = ''  # Add your Reddit password

# OpenAI API Key
OPENAI_API_KEY = ''  # Replace with your OpenAI API key
openai.api_key = OPENAI_API_KEY

# List of Supercell-related subreddits
subreddits = ['BrawlStars', 'ClashOfClans', 'ClashRoyale']

CATEGORIES = ["Bug", "Feature Request", "Positive", "Negative", "Other"]

def clean_comments(comments):
    """
    Cleans a list of Reddit comments by removing emojis, special characters, URLs, and lowercasing text.
    Returns a list of cleaned comments.
    """
    url_pattern = re.compile(r'https?://\S+|www\.\S+')
    emoji_pattern = re.compile(
        "["
        u"\U0001F600-\U0001F64F"  # emoticons
        u"\U0001F300-\U0001F5FF"  # symbols & pictographs
        u"\U0001F680-\U0001F6FF"  # transport & map symbols
        u"\U0001F1E0-\U0001F1FF"  # flags (iOS)
        u"\U00002700-\U000027BF"  # Dingbats
        u"\U000024C2-\U0001F251"  # Enclosed characters
        "]+", flags=re.UNICODE)
    special_pattern = re.compile(r'[^a-zA-Z0-9\s]')

    cleaned = []
    for comment in comments:
        text = url_pattern.sub('', comment)
        text = emoji_pattern.sub('', text)
        text = special_pattern.sub('', text)
        text = text.lower()
        text = text.strip()
        if text:
            cleaned.append(text)
    return cleaned

def categorize_comments(comments, batch_size=10, max_retries=3):
    """
    Sends batches of comments to OpenAI API and receives categorized feedback.
    Returns a list of dicts: [{"comment": ..., "category": ...}, ...]
    """
    import json
    results = []
    for i in range(0, len(comments), batch_size):
        batch = comments[i:i+batch_size]
        prompt = (
            "Categorize each Reddit comment into one of the following categories: "
            f"{', '.join(CATEGORIES)}.\n"
            "Return a JSON list of objects with 'comment' and 'category'.\n"
            "Comments:\n" + '\n'.join(f"- {c}" for c in batch)
        )
        for attempt in range(max_retries):
            try:
                response = openai.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0
                )
                content = response.choices[0].message.content
                if content is None:
                    print(f"OpenAI response content is None in batch {i//batch_size+1}, attempt {attempt+1}")
                    continue
                batch_results = json.loads(content)
                results.extend(batch_results)
                break
            except Exception as e:
                print(f"Error in batch {i//batch_size+1}, attempt {attempt+1}: {e}")
                time.sleep(2)
        else:
            print(f"Failed to process batch {i//batch_size+1} after {max_retries} attempts.")
    return results

def summarize_feedback(df, output_file='reddit_feedback_summary.txt', top_n_words=5, example_n=2):
    """
    Summarizes categorized feedback: number of each category, most common words in each category, and example comments.
    Outputs the summary to a text file.
    """
    from collections import Counter
    import string

    summary_lines = []
    categories = df['category'].unique()
    for cat in categories:
        cat_df = df[df['category'] == cat]
        count = len(cat_df)
        # Tokenize and count words
        words = (
            ' '.join(cat_df['original_comment'])
            .lower()
            .translate(str.maketrans('', '', string.punctuation))
            .split()
        )
        word_counts = Counter(words)
        common_words = ', '.join([f"{w} ({c})" for w, c in word_counts.most_common(top_n_words)])
        # Example comments
        examples = cat_df['original_comment'].head(example_n).tolist()
        summary_lines.append(f"Category: {cat}")
        summary_lines.append(f"Count: {count}")
        summary_lines.append(f"Most common words: {common_words if common_words else 'N/A'}")
        summary_lines.append("Example comments:")
        for ex in examples:
            summary_lines.append(f"- {ex[:200]}")
        summary_lines.append("")
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write('\n'.join(summary_lines))
    print(f"\nSummary written to {output_file}")

def main():
    reddit = praw.Reddit(
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        user_agent=USER_AGENT,
        username=USERNAME,
        password=PASSWORD
    )

    data = []
    for subreddit_name in subreddits:
        print(f"\nFetching comments from r/{subreddit_name}...")
        subreddit = reddit.subreddit(subreddit_name)
        for submission in subreddit.hot(limit=5):  # Limit to 5 hot posts for demo
            print(f"\nPost: {submission.title}")
            submission.comments.replace_more(limit=0)
            comments = [comment for comment in submission.comments.list()]
            original_bodies = [comment.body for comment in comments]
            timestamps = [comment.created_utc for comment in comments]
            cleaned_comments = clean_comments(original_bodies)
            categorized = categorize_comments(cleaned_comments)
            for idx, item in enumerate(categorized):
                data.append({
                    'original_comment': original_bodies[idx],
                    'timestamp': timestamps[idx],
                    'subreddit': subreddit_name,
                    'category': item['category']
                })
                print(f"- [{item['category']}] {original_bodies[idx][:100]}")
    # Create DataFrame and export to CSV
    df = pd.DataFrame(data)
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s')
    df.to_csv('reddit_comments_categorized.csv', index=False)
    print('\nExported categorized comments to reddit_comments_categorized.csv')
    summarize_feedback(df)

if __name__ == "__main__":
    main()
