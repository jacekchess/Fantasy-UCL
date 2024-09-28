from bs4 import BeautifulSoup
from selenium import webdriver
from typing import List, Tuple
from team_id_dict import TEAM_ID
import pickle
import re
import pandas as pd
import os.path
import numpy as np


def getClubs(url: str="https://www.uefa.com/uefachampionsleague/clubs/") -> Tuple[List[str], List[str]]:
    """Get list of clubs and links to the club pages on uefa champions league webpage

    Args:
        url (str, optional): Link to the uefa webpage with club names. Defaults to "https://www.uefa.com/uefachampionsleague/clubs/".

    Returns:
        Tuple[List[str], List[str]]: List of club names and list of links
    """
    # Initialize webdriver and get content
    driver = webdriver.Chrome()
    driver.get(url)
    page_content = driver.page_source
    driver.quit()

    # Extract information
    soup = BeautifulSoup(page_content, features="html.parser")
    clubs_table = soup.select("div.teams-overview_teams-wrapper")[0]
    clubs = clubs_table.find_all("a", {"class" : "team-wrap"})
    names = [club.get("title") for club in clubs]
    links = [club.get("href") for club in clubs] # /uefachampionsleague/clubs/50031--young-boys/

    return names, links


def getWhoScoredLinks(names: List[str], url: str="https://www.whoscored.com/Teams/", path: str="scraping/player_links.pickle") -> None:
    """Get links to the players at WhoScored webpage and save them to the path.

    Args:
        names (List[str]): Names of the clubs (from getClubs function)
        url (str, optional): Endpoint for the WhoScored teams. Defaults to "https://www.whoscored.com/Teams/".
        path (str, optional): Path where the results will be written to. Defaults to "scraping/player_links.pickle".
    """
    all_links = []
    for name in names:
        # Translate team name to id
        id = TEAM_ID[name]

        # Initialize webdriver and get content for a club
        driver = webdriver.Chrome()
        driver.get(f"{url}{id}/")
        page_content = driver.page_source
        driver.quit()

        # Extract links to every player of the club
        soup = BeautifulSoup(page_content, features="html.parser")
        stat_table = soup.find("div", {"id": "statistics-table-summary"})
        players = stat_table.find_all("a", {"class" : "player-link"})
        links = [player.get("href") for player in players]
        all_links.append(links)
        
    # Save results as a pickle (list of lists where every inner list holds players from one club)
    with open(path, "wb") as f:
        pickle.dump(all_links, f)
        

def getPlayersData(players_path: str="scraping/player_links.pickle", data_path: str="data/raw.csv") -> None:
    """Get all player statistics per game from whoscored and save it to the data_path.

    Args:
        players_path (str, optional): Path to the list with player links (from getWhoScoredLinks). Defaults to "scraping/player_links.pickle".
        data_path (str, optional): Path where results will be written to. Defaults to "data/raw.csv".
    """
    # Load player links
    with open(players_path, "rb") as f:
        links = pickle.load(f)
    
    links_flat = [link for club in links for link in club]
    links_flat = list(set(links_flat))

    # Load or create dataset
    if os.path.isfile(data_path):
        data = pd.read_csv(data_path)
        processed_names = data.Name.unique()
    else:
        data = pd.DataFrame(columns=['Name','Club','Nationality','Date','Home','Away','Result','Minutes','Ratings','Yellow','Red','Goals','Assists','MOM'])
        processed_names = []

    for link in links_flat:

        # Process only players that are not in a dataset already (TODO: can be improved for continous flow)
        player_name = link.split("/")[-1].replace("-", " ")
        if player_name in processed_names:
            continue
            
        try:
            # Initialize webdriver and get content for a player
            driver = webdriver.Chrome()
            driver.get(f"https://www.whoscored.com/{link}")
            page_content = driver.page_source
            driver.quit()
            
            soup = BeautifulSoup(page_content, features="html.parser")
            
            # Get player team and nationality
            player_info = soup.find("div", {"class": "col12-lg-10 col12-m-10 col12-s-9 col12-xs-8"})
            player_team = player_info.find("a", {"class": "team-link"}).contents[0]
            player_nationality = player_info.find("span", {"class": "iconize iconize-icon-left"}).contents[0]
            
            stat_table = soup.find("div", {"id": "player-matches-table"})

            # Get match dates
            dates = stat_table.find_all("div", {"class" : "col12-lg-1 col12-m-2 col12-s-0 col12-xs-0 divtable-data date-long"})
            dates = [date.find("div").contents[0] for date in dates]

            # Get Home team names
            home_teams = stat_table.find_all("div", {"class" : "home-team"})
            home_teams = [team.find("a").contents[0] for team in home_teams]

            # Get away team names
            away_teams = stat_table.find_all("div", {"class" : "away-team"})
            away_teams = [team.find("a").contents[0] for team in away_teams]

            # Get match result
            results = stat_table.find_all("div", {"class" : "player-match-result"})
            results = [result.find("a").contents[0] for result in results]

            # Get number of minutes played by a player in each game
            minutes = stat_table.find_all("div", {"title" : "Minutes played in this match"})
            minutes = [re.sub("[^0-9]", "", minut.contents[0]) for minut in minutes]

            # Get player ratings for each game
            ratings = stat_table.find_all("div", {"title" : "Rating in this match"})
            ratings = [re.sub("[^0-9\.]", "", rating.contents[0]) for rating in ratings]

            # Count number of incidents for a player in each match
            incidents = stat_table.find_all("div", {"class" : "col12-lg-3 col12-m-2 col12-s-3 col12-xs-3 divtable-data match-icons"})
            incidents = [incident.find_all("span", {"class" : "incident-wrapper"}) for incident in incidents]

            # Incidents involve yellow cards, red cards, man of the match awards, goals, and assists
            yellow_cards = [0 if len(incident) == 0 else sum([1 if i.find("span").get("title") == 'Yellow Card' else 0 for i in incident]) for incident in incidents]
            red_cards = [0 if len(incident) == 0 else sum([1 if i.find("span").get("title") == 'Red Card' else 0 for i in incident]) for incident in incidents]
            man_of_the_match = [0 if len(incident) == 0 else sum([1 if i.find("span").get("title") == 'Man of the match' else 0 for i in incident]) for incident in incidents]
            goals = [0 if len(incident) == 0 else sum([1 if i.find("span").get("title") == 'Goal' else 0 for i in incident]) for incident in incidents]
            assists = [0 if len(incident) == 0 else sum([1 if i.find("span").get("title") == 'Assist' else 0 for i in incident]) for incident in incidents]

            # Save data
            n = len(dates)
            temp = pd.DataFrame({'Name': [player_name]*n,'Club': [player_team]*n,'Nationality':[player_nationality]*n,
                        'Date': dates,'Home': home_teams,'Away': away_teams,'Result': results,'Minutes': minutes,
                        'Ratings': ratings,'Yellow': yellow_cards,'Red': red_cards,'Goals': goals,'Assists': assists,'MOM': man_of_the_match})
            
            data = pd.concat([data, temp])
            data.to_csv(data_path, index=False)
            processed_names = np.append(player_name, processed_names)

        except Exception as e:
            print(f"While procesing {player_name} exception occured: {e}")
        

# names, _ = getClubs()
# names = ['Arsenal', 'Aston Villa', 'Atalanta', 'Atleti', 'B. Dortmund', 'Barcelona', 'Bayern München', 'Benfica', 'Bologna', 'Brest', 'Celtic', 'Club Brugge', 'Crvena Zvezda', 'Feyenoord', 'Girona', 'GNK Dinamo', 'Inter', 'Juventus', 'Leipzig', 'Leverkusen', 'Lille', 'Liverpool', 'Man City', 'Milan', 'Monaco', 'Paris', 'PSV', 'Real Madrid', 'S. Bratislava', 'Salzburg', 'Shakhtar', 'Sparta Praha', 'Sporting CP', 'Sturm Graz', 'Stuttgart', 'Young Boys']
# getWhoScoredLinks(names)
# getPlayersData()
