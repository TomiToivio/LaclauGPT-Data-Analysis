import feedparser
d = feedparser.parse('https://bengoertzel.substack.com/feed')
print(d)
for item in d.entries:
    print(item.title)
    print(item.link)
    print(item.description)
    print(item.published)
    print(item.published_parsed)
#title = d.feed.title
#link = d.feed.link
#description = d.feed.description
#published = d.feed.published
#published_parsed = d.feed.published_parsed
#print(title)
#print(link)
#print(description)
#print(published)
#print(published_parsed)