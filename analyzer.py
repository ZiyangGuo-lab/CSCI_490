import re
import numpy as np
import pandas as pd
from pprint import pprint

# Gensim
import gensim
import gensim.corpora as corpora
from gensim.utils import simple_preprocess
from gensim.models import CoherenceModel
import pyLDAvis.gensim_models

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

    def __init__(self, df: pd.DataFrame, postfix=""):
        self.df = df
        Analyzer.output_file_path = "LDA_results/LDA_result" + postfix +".txt"
        if os.path.exists(Analyzer.output_file_path):
            os.remove(Analyzer.output_file_path)


    def analyze(self, test_alpha='auto', test_beta='auto'):
        logging.basicConfig(format='%(asctime)s : %(levelname)s : %(message)s', level=logging.ERROR)
        warnings.filterwarnings("ignore", category=DeprecationWarning)

        stop_words = stopwords.words('english')

        df = self.df
        df.head()

        # Convert to list
        data = df.tweet.values.tolist()

        # Remove new line characters
        data = [re.sub('\s+', ' ', str(sent)) for sent in data]

        # Remove distracting single quotes
        data = [re.sub("\'", "", str(sent)) for sent in data]

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
                                                    num_topics=25,
                                                    random_state=100,
                                                    update_every=1,
                                                    chunksize=100,
                                                    passes=10,
                                                    alpha=test_alpha,
                                                    per_word_topics=True,
                                                    eta = test_beta)
                                                
        print_and_write("alpha:", lda_model.alpha, "beta:", lda_model.eta)

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

        # Visualize the topics
        vis = pyLDAvis.gensim_models.prepare(lda_model, corpus, id2word, mds='mmds')
        pyLDAvis.save_html(vis, 'lda.html')







        # Build LDA Mallet Model
        mallet_path = "./mallet-2.0.8/bin/mallet"

        ldamallet = gensim.models.wrappers.LdaMallet(mallet_path, corpus=corpus, num_topics=20, id2word=id2word)
        print_and_write(ldamallet.show_topics(formatted=False), func=pprint)

        coherence_model_ldamallet = CoherenceModel(model=ldamallet, texts=data_lemmatized, dictionary=id2word, coherence='c_v')
        coherence_ldamallet = coherence_model_ldamallet.get_coherence()
        print_and_write('\nCoherence Score: ', coherence_ldamallet)

        # Find the optimal number of topics for LDA
        def compute_coherence_values(dictionary, corpus, texts, limit, start=2, step=3):
            """
            Compute c_v coherence for various number of topics

            Parameters:
            ----------
            dictionary : Gensim dictionary
            corpus : Gensim corpus
            texts : List of input texts
            limit : Max num of topics

            Returns:
            -------
            model_list : List of LDA topic models
            coherence_values : Coherence values corresponding to the LDA model with respective number of topics
            """
            coherence_values = []
            model_list = []
            for num_topics in range(start, limit, step):
                model = gensim.models.wrappers.LdaMallet(mallet_path, corpus=corpus, num_topics=num_topics, id2word=id2word)
                model_list.append(model)
                coherencemodel = CoherenceModel(model=model, texts=texts, dictionary=dictionary, coherence='c_v')
                coherence_values.append(coherencemodel.get_coherence())

            return model_list, coherence_values

        model_list, coherence_values = compute_coherence_values(dictionary=id2word, corpus=corpus, texts=data_lemmatized, start=2, limit=40, step=6)
        limit=40
        start=2
        step=6
        x = range(start, limit, step)
        # plt.plot(x, coherence_values)
        # plt.xlabel("Num Topics")
        # plt.ylabel("Coherence score")
        # plt.legend(("coherence_values"), loc='best')
        # plt.show()
        prev_cv = 0
        optimal_model = None
        for m, cv, model in zip(x, coherence_values, model_list):
            print_and_write("Num Topics =", m, " has Coherence Value of", round(cv, 4))
            if cv > prev_cv:
                prev_cv = cv
                optimal_model = model

        # Finding the dominant topic in each sentence
        def format_topics_sentences(ldamodel=lda_model, corpus=corpus, texts=data):
            # Init output
            sent_topics_df = pd.DataFrame()

            # Get main topic in each document
            for i, row in enumerate(ldamodel[corpus]):
                row = sorted(row, key=lambda x: (x[1]), reverse=True)
                # Get the Dominant topic, Perc Contribution and Keywords for each document
                for j, (topic_num, prop_topic) in enumerate(row):
                    if j == 0:  # => dominant topic
                        wp = ldamodel.show_topic(topic_num)
                        topic_keywords = ", ".join([word for word, prop in wp])
                        sent_topics_df = sent_topics_df.append(pd.Series([int(topic_num), round(prop_topic,4), topic_keywords]), ignore_index=True)
                    else:
                        break
            sent_topics_df.columns = ['Dominant_Topic', 'Perc_Contribution', 'Topic_Keywords']

            # Add original text to the end of the output
            contents = pd.Series(texts)
            sent_topics_df = pd.concat([sent_topics_df, contents], axis=1)
            return(sent_topics_df)

        df_topic_sents_keywords = format_topics_sentences(ldamodel=optimal_model, corpus=corpus, texts=data)

        # Format
        df_dominant_topic = df_topic_sents_keywords.reset_index()
        df_dominant_topic.columns = ['Document_No', 'Dominant_Topic', 'Topic_Perc_Contrib', 'Keywords', 'Text']

        # Show
        df_dominant_topic.head(10)

        # Group top 5 sentences under each topic
        sent_topics_sorteddf_mallet = pd.DataFrame()

        sent_topics_outdf_grpd = df_topic_sents_keywords.groupby('Dominant_Topic')

        for i, grp in sent_topics_outdf_grpd:
            sent_topics_sorteddf_mallet = pd.concat([sent_topics_sorteddf_mallet, 
                                                    grp.sort_values(['Perc_Contribution'], ascending=[0]).head(1)], 
                                                    axis=0)

        # Reset Index    
        sent_topics_sorteddf_mallet.reset_index(drop=True, inplace=True)

        # Format
        sent_topics_sorteddf_mallet.columns = ['Topic_Num', "Topic_Perc_Contrib", "Keywords", "Text"]

        # Show
        sent_topics_sorteddf_mallet.head()


        # Number of Documents for Each Topic
        topic_counts = df_topic_sents_keywords['Dominant_Topic'].value_counts()

        # Percentage of Documents for Each Topic
        topic_contribution = round(topic_counts/topic_counts.sum(), 4)

        # Topic Number and Keywords
        topic_num_keywords = df_topic_sents_keywords[['Dominant_Topic', 'Topic_Keywords']]

        # Concatenate Column wise
        df_dominant_topics = pd.concat([topic_num_keywords, topic_counts, topic_contribution], axis=1)

        # Change Column names
        df_dominant_topics.columns = ['Dominant_Topic', 'Topic_Keywords', 'Num_Documents', 'Perc_Documents']

        # Show
        df_dominant_topics