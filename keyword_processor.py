from flashtext import KeywordProcessor

keyword_processor = KeywordProcessor()

file_path = "keywords.txt"

with open(file_path, 'r', encoding="utf-8") as f:
    keywords = [line.strip() for line in f if line.strip()]

for word in keywords:
    keyword_processor.add_keyword(word, '*' * len(word))

def remove_keyword(keyword: str):
    keyword_processor.remove_keyword(keyword)
    with open(file_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    filtered_lines = [line for line in lines if line.strip() != keyword]

    with open("keywords.txt", "w", encoding="utf-8") as file:
        file.writelines(filtered_lines)


def filter_text(text: str) -> str:
    return keyword_processor.replace_keywords(text)
