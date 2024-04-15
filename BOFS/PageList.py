from flask import current_app, request
from BOFS import util


class PageList(object):
    page_list = []

    def __init__(self, page_list):
        self.page_list = page_list

    def unconditional_pages(self):
        pages = []
        for entry in self.page_list:
            if 'conditional_routing' in entry:
                continue
            pages.append(entry)

        return pages

    def conditional_pages(self, condition):
        pages = []

        for entry in self.page_list:
            if 'conditional_routing' in entry:
                for conditional_route in entry['conditional_routing']:
                    if conditional_route['condition'] == condition:
                        for conditional_entry in conditional_route['page_list']:
                            pages.append(conditional_entry)
                        break  # once a match has been found, then we're done

        return pages

    def flat_page_list(self, condition=None) -> list[str]:
        """
        This is the typical access point for the page_list variable.
        By default, it tries to get the current condition from the session variable.
        :param condition: Set this to override the default functionality
        :return:
        """
        if condition is None:
            condition = util.fetch_current_condition()

        flat_page_list = list()

        for entry in self.page_list:
            if 'conditional_routing' in entry:
                for conditional_route in entry['conditional_routing']:
                    if condition == 0 or conditional_route['condition'] == condition:
                        for conditional_entry in conditional_route['page_list']:
                            flat_page_list.append(conditional_entry)
                        break  # once a match has been found, then we're done
            else:
                flat_page_list.append(entry)

        return flat_page_list

    def get_questionnaire_list(self, include_tags=False) -> list[str]:
        """
        Returns a list of the questionnaires specified in the config's PAGE_LIST variable.
        :param bool include_tags: if true, then the paths will be in the format <questionnaire>/<tag>.
        :returns: list -- one entry per questionnaire, the filename of the questionnaire (without the .json).
        """
        condition_count = util.fetch_condition_count()
        questionnaires: list[str] = list()

        for page in self.unconditional_pages():
            if not page['path'].startswith("questionnaire/"):
                continue  # Not a questionnaire

            questionnaire_name = page['path'].replace("questionnaire/", "", 1)

            if not include_tags:
                questionnaire_name = questionnaire_name.split("/")[0]

            questionnaires.append(questionnaire_name)

        for condition in range(1, condition_count+1):
            for page in self.conditional_pages(condition):
                if not page['path'].startswith("questionnaire/"):
                    continue  # Not a questionnaire

                questionnaire_name = page['path'].replace("questionnaire/", "", 1)

                if not include_tags:
                    questionnaire_name = questionnaire_name.split("/")[0]

                # The same questionnaire may appear in multiple conditions, so don't add it again.
                if questionnaire_name not in questionnaires:
                    questionnaires.append(questionnaire_name)

        return questionnaires

    def get_index(self, path):
        """
        This function determines which index a path is within the ``flat_page_list()`` list.
        :param str path: the path to determine the index of.
        :returns: int -- the index of the path

        .. note::
            * Uses startswith() to determine a match.
            * Paths will have their leading forward-slash removed, if it exists.
        """
        if path.startswith("/"):
            path = path[1:]
        for i, page in enumerate(self.flat_page_list()):
            if page['path'] == path:
                return i
        return None

    def next_path(self, current_path=None):
        """
        Gives the next path from ``flat_page_list()``, based on incrementing the index of the current path.
        :param str current_path: The user's current path
        :returns: str -- the next path in ``flat_page_list()`` which the user should be sent to.
        """
        if current_path is None:
            current_path = request.path
        if current_path.startswith("/"):
            path = current_path[1:]
        current_index = self.get_index(current_path)
        flat_page_list = self.flat_page_list()

        if current_index == len(flat_page_list) - 1:
            return current_path

        return flat_page_list[current_index + 1]['path']

    def previous_path(self, current_path=None):
        """
        Gives the previous path from ``flat_page_list()``, based on incrementing the index of the current path.
        :param str current_path: The user's current path
        :returns: str -- the next path in ``flat_page_list()`` which the user should be sent to.
        """
        if current_path is None:
            current_path = request.path
        if current_path.startswith("/"):
            current_path = current_path[1:]

        current_index = self.get_index(current_path)

        if current_index == 0:
            return current_path

        return self.flat_page_list()[current_index - 1]['path']
