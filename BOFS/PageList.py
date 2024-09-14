from typing import Union
from flask import current_app, request
from BOFS import util
from urllib.parse import urlsplit


class PageList(object):
    page_list = []
    procedure = []

    def __init__(self, page_list):
        self.page_list = page_list
        #self.procedure = self.parse_list_into_procedure()

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

    @staticmethod
    def extract_questionnaire_from_path(path, include_tag=False):
        questionnaire = path.replace("questionnaire/", "", 1)

        if not include_tag:
            questionnaire_name = questionnaire.split("/")[0]

        return questionnaire

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

            questionnaire_name = self.extract_questionnaire_from_path(page['path'], include_tags)
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

    def parse_list_into_procedure(self) -> list[Union[str, dict]]:
        procedure = []
        for entry in self.page_list:
            if 'conditional_routing' not in entry:
                #questionnaire_name = self.extract_questionnaire_from_path(entry['path'], False)
                procedure.append(entry)
            else:
                # Need to work out the page list lengths for each condition, so I don't end up accessing an invalid index.
                page_list_lengths = {}
                max_length = 0
                for cr_option in entry['conditional_routing']:
                    list_length = len(cr_option['page_list'])
                    page_list_lengths[cr_option['condition']] = list_length

                    if list_length > max_length:
                        max_length = list_length

                for i in range(max_length):
                    new_sub_list = {}
                    for cr_option in entry['conditional_routing']:
                        cr_condition = cr_option['condition']
                        new_sub_list[cr_condition] = None

                        if page_list_lengths[cr_condition] > i:  # Then it's safe to access the page entry
                            #questionnaire_name = self.extract_questionnaire_from_path(cr_option['page_list'][i]['path'], False)
                            new_sub_list[cr_condition] = cr_option['page_list'][i]

                    procedure.append(new_sub_list)

        return procedure

    def to_mermaid(self):
        def mermaid_entry_to_syntax(entry) -> str:
            return f"{entry['name']}(\"<b>{entry['header']}</b><br>{entry['text']}\")"

        def parse_until_cr(page_list, mermaid_entries, name_prefix=""):
            index_reached = 0

            if mermaid_entries is None:
                mermaid_entries = []

            for entry in page_list:
                if "conditional_routing" in entry:
                    break  # End early

                idx = len(mermaid_entries)
                path = entry['path'].replace("questionnaire/", "")

                if len(mermaid_entries) > 0 and 'header' in mermaid_entries[-1] and mermaid_entries[-1]['header'] == entry['name']:
                    mermaid_entries[-1]['text'] += f"<br>{path}"
                else:
                    mermaid_entries.append({'name': f"{name_prefix}{idx}", 'header': entry['name'], 'text': path})
                index_reached += 1

            return page_list[index_reached:]  # Return the remaining pages

        mermaid_entries = []
        page_list_copy = self.page_list[:]

        while len(page_list_copy) > 0:
            if "conditional_routing" in page_list_copy[0]:

                conditional_entries = {}
                for cr in page_list_copy[0]['conditional_routing']:
                    name_prefix = f"{len(mermaid_entries)}_cr_{cr['condition']}_"
                    conditional_entries[cr["condition"]] = []

                    parse_until_cr(cr['page_list'], conditional_entries[cr["condition"]], name_prefix)

                page_list_copy = page_list_copy[1:]

                    #sub_idx = 0
                    #conditional_entries[cr["condition"]] = []
                    #
                    #for cr_entry in cr['page_list']:
                    #    name = f"{idx}_{sub_idx}_{cr['condition']}"
                    #    conditional_entries[cr["condition"]].append({
                    #        'name': name,
                    #        'text': entry_to_mermaid_syntax(name, cr_entry)
                    #    })
                    #    sub_idx += 1

                mermaid_entries.append(conditional_entries)
            #idx += 1

            page_list_copy = parse_until_cr(page_list_copy, mermaid_entries)

        # for entry in self.page_list:
        #     if "conditional_routing" not in entry:
        #         entry_text = entry_to_mermaid_syntax(idx, entry)
        #         mermaid_entries.append({'name': idx, 'text': entry_text})
        #
        #     else:
        #         conditional_entries = {}
        #         for cr in entry['conditional_routing']:
        #             sub_idx = 0
        #             conditional_entries[cr["condition"]] = []
        #
        #             for cr_entry in cr['page_list']:
        #                 name = f"{idx}_{sub_idx}_{cr['condition']}"
        #                 conditional_entries[cr["condition"]].append({
        #                     'name': name,
        #                     'text': entry_to_mermaid_syntax(name, cr_entry)
        #                 })
        #                 sub_idx += 1
        #         mermaid_entries.append(conditional_entries)
        #     idx += 1

        output_str = "flowchart TB\n"

        first = True
        last_entry = None
        cr_idx = 0

        for entry in mermaid_entries:
            if 'text' in entry:
                if not first:
                    output_str += "-->"
                output_str += mermaid_entry_to_syntax(entry)
                first = False
                last_entry = entry
            else:
                #output_str += f"\nsubgraph conditional_routing_{cr_idx}"
                #cr_idx += 1
                last_ids = {}

                for condition in entry:
                    output_str += "\n"
                    output_str += f"{last_entry['name']}"

                    for subidx, subentry in enumerate(entry[condition]):
                        output_str += "-->"
                        output_str += mermaid_entry_to_syntax(subentry)
                        last_ids[condition] = subentry['name']

                #output_str += "\nend\n"
                output_str += "\n"
                output_str += " & ".join(last_ids.values())

        #output_str += "-->".join([entry['text'] for entry in mermaid_entries])

        return output_str

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
        if current_path == '/redirect_next_page':
            parsed = urlsplit(request.referrer)
            current_path = parsed.path
        if current_path.startswith("/"):
            current_path = current_path[1:]
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
