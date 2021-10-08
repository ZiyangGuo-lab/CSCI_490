import re
import numpy as np
import pandas as pd
from pprint import pprint

# Gensim
import gensim
import gensim.corpora as corpora
from gensim.utils import simple_preprocess
from gensim.models import CoherenceModel

# spacy for lemmatization
import spacy

# Plotting tools
import pyLDAvis
import pyLDAvis.gensim_models # don't skip this
import matplotlib.pyplot as plt
# %matplotlib inline

# Enable logging for gensim - optional
import logging
import os

import warnings
from nltk.corpus import stopwords

import contextlib


def print_and_write(*target: str or (str),  func=print):
    with open(Analyzer.output_file_path, "a") as o:
        with contextlib.redirect_stdout(o):
            print(target)
    func(target)

class Analyzer:
    output_file_path = "LDA_result.txt"

    def __init__(self, df: pd.DataFrame):
        self.df = df
        if os.path.exists(Analyzer.output_file_path):
            os.remove(Analyzer.output_file_path)


    def analyze(self):
        logging.basicConfig(format='%(asctime)s : %(levelname)s : %(message)s', level=logging.ERROR)
        warnings.filterwarnings("ignore", category=DeprecationWarning)

        stop_words = stopwords.words('english')

        df = self.df
        df.head()

        # Convert to list
        data = df.tweet.values.tolist()

        # Remove new line characters
        data = [re.sub('\s+', ' ', sent) for sent in data]

        # Remove distracting single quotes
        data = [re.sub("\'", "", sent) for sent in data]

        print_and_write(data[:1], func=pprint)

        def sent_to_words(sentences):
            for sentence in sentences:
                yield (gensim.utils.simple_preprocess(str(sentence), deacc=True))  # deacc=True removes punctuations

        data_words = list(sent_to_words(data))

        print_and_write(data_words[:1])

        # Build the bigram and trigram models
        bigram = gensim.models.Phrases(data_words, min_count=5, threshold=100)  # higher threshold fewer phrases.
        trigram = gensim.models.Phrases(bigram[data_words], threshold=100)

        # Faster way to get a sentence clubbed as a trigram/bigram
        bigram_mod = gensim.models.phrases.Phraser(bigram)
        trigram_mod = gensim.models.phrases.Phraser(trigram)

        # See trigram example
        print_and_write(trigram_mod[bigram_mod[data_words[0]]])

        # Define functions for stopwords, bigrams, trigrams and lemmatization
        def remove_stopwords(texts):
            return [[word for word in simple_preprocess(str(doc)) if word not in stop_words] for doc in texts]

        def make_bigrams(texts):
            return [bigram_mod[doc] for doc in texts]

        def make_trigrams(texts):
            return [trigram_mod[bigram_mod[doc]] for doc in texts]

        def lemmatization(texts, allowed_postags=['NOUN', 'ADJ', 'VERB', 'ADV']):
            """https://spacy.io/api/annotation"""
            texts_out = []
            for sent in texts:
                doc = nlp(" ".join(sent))
                texts_out.append([token.lemma_ for token in doc if token.pos_ in allowed_postags])
            return texts_out

        # Remove Stop Words
        data_words_nostops = remove_stopwords(data_words)

        # Form Bigrams
        data_words_bigrams = make_bigrams(data_words_nostops)

        # Initialize spacy 'en' model, keeping only tagger component (for efficiency)
        # python3 -m spacy download en
        nlp = spacy.load('en_core_web_sm', disable=['parser', 'ner'])

        # Do lemmatization keeping only noun, adj, vb, adv
        data_lemmatized = lemmatization(data_words_bigrams, allowed_postags=['NOUN', 'ADJ', 'VERB', 'ADV'])

        print_and_write(data_lemmatized[:1])

        # Create Dictionary
        id2word = corpora.Dictionary(data_lemmatized)

        # Create Corpus
        texts = data_lemmatized

        # Term Document Frequency
        corpus = [id2word.doc2bow(text) for text in texts]

        # View
        print_and_write([[(id2word[id], freq) for id, freq in cp] for cp in corpus[:1]])

        # Build LDA model
        lda_model = gensim.models.ldamodel.LdaModel(corpus=corpus,
                                                    id2word=id2word,
                                                    num_topics=20,
                                                    random_state=100,
                                                    update_every=1,
                                                    chunksize=100,
                                                    passes=10,
                                                    alpha='auto',
                                                    per_word_topics=True)

        # Print the Keyword in the 10 topics
        print_and_write(lda_model.print_topics(), func=pprint)
        doc_lda = lda_model[corpus]

        # Compute Perplexity
        print_and_write('\nPerplexity: ',
              lda_model.log_perplexity(corpus))  # a measure of how good the model is. lower the better.

        # Compute Coherence Score
        coherence_model_lda = CoherenceModel(model=lda_model, texts=data_lemmatized, dictionary=id2word,
                                             coherence='c_v')
        coherence_lda = coherence_model_lda.get_coherence()
        print_and_write('\nCoherence Score: ', coherence_lda)


