# -*- coding: utf-8 -*-
# Copyright (C) 2014-2016 Andrey Antukh <niwi@niwi.nz>
# Copyright (C) 2014-2016 Jesús Espino <jespinog@gmail.com>
# Copyright (C) 2014-2016 David Barragán <bameda@dbarragan.com>
# Copyright (C) 2014-2016 Alejandro Alonso <alejandro.alonso@kaleidos.net>
# Copyright (C) 2014-2016 Anler Hernández <hello@anler.me>
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import uuid
import csv

from unittest import mock
from django.core.urlresolvers import reverse

from taiga.base.utils import json
from taiga.projects.userstories import services, models

from .. import factories as f

import pytest
pytestmark = pytest.mark.django_db


def test_get_userstories_from_bulk():
    data = "User Story #1\nUser Story #2\n"
    userstories = services.get_userstories_from_bulk(data)

    assert len(userstories) == 2
    assert userstories[0].subject == "User Story #1"
    assert userstories[1].subject == "User Story #2"


def test_create_userstories_in_bulk():
    data = "User Story #1\nUser Story #2\n"

    with mock.patch("taiga.projects.userstories.services.db") as db:
        userstories = services.create_userstories_in_bulk(data)
        db.save_in_bulk.assert_called_once_with(userstories, None, None)


def test_update_userstories_order_in_bulk():
    project = f.ProjectFactory.create()
    us1 = f.UserStoryFactory.create(project=project, backlog_order=1)
    us2 = f.UserStoryFactory.create(project=project, backlog_order=2)
    data = [{"us_id": us1.id, "order": 1}, {"us_id": us2.id, "order": 2}]

    with mock.patch("taiga.projects.userstories.services.db") as db:
        services.update_userstories_order_in_bulk(data, "backlog_order", project)
        db.update_attr_in_bulk_for_ids.assert_called_once_with({us1.id: 1, us2.id: 2},
                                                                "backlog_order",
                                                                models.UserStory)


def test_create_userstory_with_watchers(client):
    user = f.UserFactory.create()
    user_watcher = f.UserFactory.create()
    project = f.ProjectFactory.create(owner=user)
    f.MembershipFactory.create(project=project, user=user, is_admin=True)
    f.MembershipFactory.create(project=project, user=user_watcher, is_admin=True)
    url = reverse("userstories-list")

    data = {"subject": "Test user story", "project": project.id, "watchers": [user_watcher.id]}
    client.login(user)
    response = client.json.post(url, json.dumps(data))

    assert response.status_code == 201
    assert response.data["watchers"] == []


def test_create_userstory_without_status(client):
    user = f.UserFactory.create()
    project = f.ProjectFactory.create(owner=user)
    status = f.UserStoryStatusFactory.create(project=project)
    project.default_us_status = status
    project.save()

    f.MembershipFactory.create(project=project, user=user, is_admin=True)
    url = reverse("userstories-list")

    data = {"subject": "Test user story", "project": project.id}
    client.login(user)
    response = client.json.post(url, json.dumps(data))
    assert response.status_code == 201
    assert response.data['status'] == project.default_us_status.id


def test_create_userstory_without_default_values(client):
    user = f.UserFactory.create()
    project = f.ProjectFactory.create(owner=user, default_us_status=None)
    f.MembershipFactory.create(project=project, user=user, is_admin=True)
    url = reverse("userstories-list")

    data = {"subject": "Test user story", "project": project.id}
    client.login(user)
    response = client.json.post(url, json.dumps(data))
    assert response.status_code == 201
    assert response.data['status'] is None


def test_api_delete_userstory(client):
    us = f.UserStoryFactory.create()
    f.MembershipFactory.create(project=us.project, user=us.owner, is_admin=True)
    url = reverse("userstories-detail", kwargs={"pk": us.pk})

    client.login(us.owner)
    response = client.delete(url)

    assert response.status_code == 204


def test_api_filter_by_subject_or_ref(client):
    user = f.UserFactory.create()
    project = f.ProjectFactory.create(owner=user)
    f.MembershipFactory.create(project=project, user=user, is_admin=True)

    f.UserStoryFactory.create(project=project)
    f.UserStoryFactory.create(project=project, subject="some random subject")
    url = reverse("userstories-list") + "?q=some subject"

    client.login(project.owner)
    response = client.get(url)
    number_of_stories = len(response.data)

    assert response.status_code == 200
    assert number_of_stories == 1, number_of_stories


def test_api_create_in_bulk_with_status(client):
    project = f.create_project()
    f.MembershipFactory.create(project=project, user=project.owner, is_admin=True)
    url = reverse("userstories-bulk-create")
    data = {
        "bulk_stories": "Story #1\nStory #2",
        "project_id": project.id,
        "status_id": project.default_us_status.id
    }

    client.login(project.owner)
    response = client.json.post(url, json.dumps(data))

    assert response.status_code == 200, response.data
    assert response.data[0]["status"] == project.default_us_status.id


def test_api_update_orders_in_bulk(client):
    project = f.create_project()
    f.MembershipFactory.create(project=project, user=project.owner, is_admin=True)
    us1 = f.create_userstory(project=project)
    us2 = f.create_userstory(project=project)

    url1 = reverse("userstories-bulk-update-backlog-order")
    url2 = reverse("userstories-bulk-update-kanban-order")
    url3 = reverse("userstories-bulk-update-sprint-order")

    data = {
        "project_id": project.id,
        "bulk_stories": [{"us_id": us1.id, "order": 1},
                         {"us_id": us2.id, "order": 2}]
    }

    client.login(project.owner)

    response1 = client.json.post(url1, json.dumps(data))
    response2 = client.json.post(url2, json.dumps(data))
    response3 = client.json.post(url3, json.dumps(data))

    assert response1.status_code == 200, response1.data
    assert response2.status_code == 200, response2.data
    assert response3.status_code == 200, response3.data


def test_api_update_milestone_in_bulk(client):
    project = f.create_project()
    f.MembershipFactory.create(project=project, user=project.owner, is_admin=True)
    us1 = f.create_userstory(project=project)
    us2 = f.create_userstory(project=project)
    milestone = f.MilestoneFactory.create(project=project)

    url = reverse("userstories-bulk-update-milestone")
    data = {
        "project_id": project.id,
        "milestone_id": milestone.id,
        "bulk_stories": [{"us_id": us1.id},
                         {"us_id": us2.id}]
    }

    client.login(project.owner)

    assert project.milestones.get(id=milestone.id).user_stories.count() == 0
    response = client.json.post(url, json.dumps(data))
    assert response.status_code == 204, response.data
    assert project.milestones.get(id=milestone.id).user_stories.count() == 2


def test_api_update_milestone_in_bulk_invalid_milestone(client):
    project = f.create_project()
    f.MembershipFactory.create(project=project, user=project.owner, is_admin=True)
    us1 = f.create_userstory(project=project)
    us2 = f.create_userstory(project=project)
    f.MilestoneFactory.create(project=project)
    m2 = f.MilestoneFactory.create()

    url = reverse("userstories-bulk-update-milestone")
    data = {
        "project_id": project.id,
        "milestone_id": m2.id,
        "bulk_stories": [{"us_id": us1.id},
                         {"us_id": us2.id}]
    }

    client.login(project.owner)

    response = client.json.post(url, json.dumps(data))
    assert response.status_code == 400
    assert response.data["non_field_errors"][0] == "the milestone isn't valid for the project"


def test_api_update_milestone_in_bulk_invalid_userstories(client):
    project = f.create_project()
    f.MembershipFactory.create(project=project, user=project.owner, is_admin=True)
    us1 = f.create_userstory(project=project)
    us2 = f.create_userstory()
    milestone = f.MilestoneFactory.create(project=project)

    url = reverse("userstories-bulk-update-milestone")
    data = {
        "project_id": project.id,
        "milestone_id": milestone.id,
        "bulk_stories": [{"us_id": us1.id},
                         {"us_id": us2.id}]
    }

    client.login(project.owner)

    response = client.json.post(url, json.dumps(data))
    assert response.status_code == 400
    assert response.data["non_field_errors"][0] == "all the user stories must be from the same project"


def test_update_userstory_points(client):
    user1 = f.UserFactory.create()
    user2 = f.UserFactory.create()
    project = f.ProjectFactory.create(owner=user1)

    role1 = f.RoleFactory.create(project=project)
    role2 = f.RoleFactory.create(project=project)

    f.MembershipFactory.create(project=project, user=user1, role=role1, is_admin=True)
    f.MembershipFactory.create(project=project, user=user2, role=role2)

    points1 = f.PointsFactory.create(project=project, value=None)
    points2 = f.PointsFactory.create(project=project, value=1)
    points3 = f.PointsFactory.create(project=project, value=2)

    us = f.UserStoryFactory.create(project=project, owner=user1, status__project=project,
                                   milestone__project=project)

    url = reverse("userstories-detail", args=[us.pk])

    client.login(user1)

    # invalid role
    data = {
        "version": us.version,
        "points": {
            str(role1.pk): points1.pk,
            str(role2.pk): points2.pk,
            "222222": points3.pk
        }
    }

    response = client.json.patch(url, json.dumps(data))
    assert response.status_code == 400

    # invalid point
    data = {
        "version": us.version,
        "points": {
            str(role1.pk): 999999,
            str(role2.pk): points2.pk
        }
    }

    response = client.json.patch(url, json.dumps(data))
    assert response.status_code == 400

    # Api should save successful
    data = {
        "version": us.version,
        "points": {
            str(role1.pk): points3.pk,
            str(role2.pk): points2.pk
        }
    }

    response = client.json.patch(url, json.dumps(data))
    assert response.data["points"][str(role1.pk)] == points3.pk


def test_update_userstory_rolepoints_on_add_new_role(client):
    # This test is explicitly without assertions. It simple should
    # works without raising any exception.

    user1 = f.UserFactory.create()
    user2 = f.UserFactory.create()
    project = f.ProjectFactory.create(owner=user1)

    role1 = f.RoleFactory.create(project=project)

    f.MembershipFactory.create(project=project, user=user1, role=role1)

    f.PointsFactory.create(project=project, value=2)

    us = f.UserStoryFactory.create(project=project, owner=user1)
    # url = reverse("userstories-detail", args=[us.pk])
    # client.login(user1)

    role2 = f.RoleFactory.create(project=project, computable=True)
    f.MembershipFactory.create(project=project, user=user2, role=role2)
    us.save()


def test_archived_filter(client):
    user = f.UserFactory.create()
    project = f.ProjectFactory.create(owner=user)
    f.MembershipFactory.create(project=project, user=user, is_admin=True)
    f.UserStoryFactory.create(project=project)
    archived_status = f.UserStoryStatusFactory.create(is_archived=True)
    f.UserStoryFactory.create(status=archived_status, project=project)

    client.login(user)

    url = reverse("userstories-list")

    data = {}
    response = client.get(url, data)
    assert len(response.data) == 2

    data = {"status__is_archived": 0}
    response = client.get(url, data)
    assert len(response.data) == 1

    data = {"status__is_archived": 1}
    response = client.get(url, data)
    assert len(response.data) == 1


def test_filter_by_multiple_status(client):
    user = f.UserFactory.create()
    project = f.ProjectFactory.create(owner=user)
    f.MembershipFactory.create(project=project, user=user, is_admin=True)
    f.UserStoryFactory.create(project=project)
    us1 = f.UserStoryFactory.create(project=project)
    us2 = f.UserStoryFactory.create(project=project)

    client.login(user)

    url = reverse("userstories-list")
    url = "{}?status={},{}".format(reverse("userstories-list"), us1.status.id, us2.status.id)

    data = {}
    response = client.get(url, data)
    assert len(response.data) == 2


def test_get_total_points(client):
    project = f.ProjectFactory.create()

    role1 = f.RoleFactory.create(project=project)
    role2 = f.RoleFactory.create(project=project)

    points1 = f.PointsFactory.create(project=project, value=None)
    points2 = f.PointsFactory.create(project=project, value=1)
    points3 = f.PointsFactory.create(project=project, value=2)

    us_with_points = f.UserStoryFactory.create(project=project)
    us_with_points.role_points.all().delete()
    f.RolePointsFactory.create(user_story=us_with_points, role=role1, points=points2)
    f.RolePointsFactory.create(user_story=us_with_points, role=role2, points=points3)

    assert us_with_points.get_total_points() == 3.0

    us_without_points = f.UserStoryFactory.create(project=project)
    us_without_points.role_points.all().delete()
    f.RolePointsFactory.create(user_story=us_without_points, role=role1, points=points1)
    f.RolePointsFactory.create(user_story=us_without_points, role=role2, points=points1)

    assert us_without_points.get_total_points() is None

    us_mixed = f.UserStoryFactory.create(project=project)
    us_mixed.role_points.all().delete()
    f.RolePointsFactory.create(user_story=us_mixed, role=role1, points=points1)
    f.RolePointsFactory.create(user_story=us_mixed, role=role2, points=points2)

    assert us_mixed.get_total_points() == 1.0


def test_api_filters_data(client):
    project = f.ProjectFactory.create()
    user1 = f.UserFactory.create(is_superuser=True)
    f.MembershipFactory.create(user=user1, project=project)
    user2 = f.UserFactory.create(is_superuser=True)
    f.MembershipFactory.create(user=user2, project=project)
    user3 = f.UserFactory.create(is_superuser=True)
    f.MembershipFactory.create(user=user3, project=project)

    status0 = f.UserStoryStatusFactory.create(project=project)
    status1 = f.UserStoryStatusFactory.create(project=project)
    status2 = f.UserStoryStatusFactory.create(project=project)
    status3 = f.UserStoryStatusFactory.create(project=project)

    tag0 = "test1test2test3"
    tag1 = "test1"
    tag2 = "test2"
    tag3 = "test3"

    # ------------------------------------------------------
    # | US    |  Owner | Assigned To | Tags                |
    # |-------#--------#-------------#---------------------|
    # | 0     |  user2 | None        |      tag1           |
    # | 1     |  user1 | None        |           tag2      |
    # | 2     |  user3 | None        |      tag1 tag2      |
    # | 3     |  user2 | None        |                tag3 |
    # | 4     |  user1 | user1       |      tag1 tag2 tag3 |
    # | 5     |  user3 | user1       |                tag3 |
    # | 6     |  user2 | user1       |      tag1 tag2      |
    # | 7     |  user1 | user2       |                tag3 |
    # | 8     |  user3 | user2       |      tag1           |
    # | 9     |  user2 | user3       | tag0                |
    # ------------------------------------------------------

    f.UserStoryFactory.create(project=project, owner=user2, assigned_to=None,
                              status=status3, tags=[tag1])
    f.UserStoryFactory.create(project=project, owner=user1, assigned_to=None,
                              status=status3, tags=[tag2])
    f.UserStoryFactory.create(project=project, owner=user3, assigned_to=None,
                              status=status1, tags=[tag1, tag2])
    f.UserStoryFactory.create(project=project, owner=user2, assigned_to=None,
                              status=status0, tags=[tag3])
    f.UserStoryFactory.create(project=project, owner=user1, assigned_to=user1,
                              status=status0, tags=[tag1, tag2, tag3])
    f.UserStoryFactory.create(project=project, owner=user3, assigned_to=user1,
                              status=status2, tags=[tag3])
    f.UserStoryFactory.create(project=project, owner=user2, assigned_to=user1,
                              status=status3, tags=[tag1, tag2])
    f.UserStoryFactory.create(project=project, owner=user1, assigned_to=user2,
                              status=status0, tags=[tag3])
    f.UserStoryFactory.create(project=project, owner=user3, assigned_to=user2,
                              status=status3, tags=[tag1])
    f.UserStoryFactory.create(project=project, owner=user2, assigned_to=user3,
                              status=status1, tags=[tag0])

    url = reverse("userstories-filters-data") + "?project={}".format(project.id)

    client.login(user1)

    # No filter
    response = client.get(url)
    assert response.status_code == 200

    assert next(filter(lambda i: i['id'] == user1.id, response.data["owners"]))["count"] == 3
    assert next(filter(lambda i: i['id'] == user2.id, response.data["owners"]))["count"] == 4
    assert next(filter(lambda i: i['id'] == user3.id, response.data["owners"]))["count"] == 3

    assert next(filter(lambda i: i['id'] is None, response.data["assigned_to"]))["count"] == 4
    assert next(filter(lambda i: i['id'] == user1.id, response.data["assigned_to"]))["count"] == 3
    assert next(filter(lambda i: i['id'] == user2.id, response.data["assigned_to"]))["count"] == 2
    assert next(filter(lambda i: i['id'] == user3.id, response.data["assigned_to"]))["count"] == 1

    assert next(filter(lambda i: i['id'] == status0.id, response.data["statuses"]))["count"] == 3
    assert next(filter(lambda i: i['id'] == status1.id, response.data["statuses"]))["count"] == 2
    assert next(filter(lambda i: i['id'] == status2.id, response.data["statuses"]))["count"] == 1
    assert next(filter(lambda i: i['id'] == status3.id, response.data["statuses"]))["count"] == 4

    assert next(filter(lambda i: i['name'] == tag0, response.data["tags"]))["count"] == 1
    assert next(filter(lambda i: i['name'] == tag1, response.data["tags"]))["count"] == 5
    assert next(filter(lambda i: i['name'] == tag2, response.data["tags"]))["count"] == 4
    assert next(filter(lambda i: i['name'] == tag3, response.data["tags"]))["count"] == 4

    # Filter ((status0 or status3)
    response = client.get(url + "&status={},{}".format(status3.id, status0.id))
    assert response.status_code == 200

    assert next(filter(lambda i: i['id'] == user1.id, response.data["owners"]))["count"] == 3
    assert next(filter(lambda i: i['id'] == user2.id, response.data["owners"]))["count"] == 3
    assert next(filter(lambda i: i['id'] == user3.id, response.data["owners"]))["count"] == 1

    assert next(filter(lambda i: i['id'] is None, response.data["assigned_to"]))["count"] == 3
    assert next(filter(lambda i: i['id'] == user1.id, response.data["assigned_to"]))["count"] == 2
    assert next(filter(lambda i: i['id'] == user2.id, response.data["assigned_to"]))["count"] == 2
    assert next(filter(lambda i: i['id'] == user3.id, response.data["assigned_to"]))["count"] == 0

    assert next(filter(lambda i: i['id'] == status0.id, response.data["statuses"]))["count"] == 3
    assert next(filter(lambda i: i['id'] == status1.id, response.data["statuses"]))["count"] == 2
    assert next(filter(lambda i: i['id'] == status2.id, response.data["statuses"]))["count"] == 1
    assert next(filter(lambda i: i['id'] == status3.id, response.data["statuses"]))["count"] == 4

    assert next(filter(lambda i: i['name'] == tag0, response.data["tags"]))["count"] == 0
    assert next(filter(lambda i: i['name'] == tag1, response.data["tags"]))["count"] == 4
    assert next(filter(lambda i: i['name'] == tag2, response.data["tags"]))["count"] == 3
    assert next(filter(lambda i: i['name'] == tag3, response.data["tags"]))["count"] == 3

    # Filter ((tag1 and tag2) and (user1 or user2))
    response = client.get(url + "&tags={},{}&owner={},{}".format(tag1, tag2, user1.id, user2.id))
    assert response.status_code == 200

    assert next(filter(lambda i: i['id'] == user1.id, response.data["owners"]))["count"] == 1
    assert next(filter(lambda i: i['id'] == user2.id, response.data["owners"]))["count"] == 1
    assert next(filter(lambda i: i['id'] == user3.id, response.data["owners"]))["count"] == 1

    assert next(filter(lambda i: i['id'] is None, response.data["assigned_to"]))["count"] == 0
    assert next(filter(lambda i: i['id'] == user1.id, response.data["assigned_to"]))["count"] == 2
    assert next(filter(lambda i: i['id'] == user2.id, response.data["assigned_to"]))["count"] == 0
    assert next(filter(lambda i: i['id'] == user3.id, response.data["assigned_to"]))["count"] == 0

    assert next(filter(lambda i: i['id'] == status0.id, response.data["statuses"]))["count"] == 1
    assert next(filter(lambda i: i['id'] == status1.id, response.data["statuses"]))["count"] == 0
    assert next(filter(lambda i: i['id'] == status2.id, response.data["statuses"]))["count"] == 0
    assert next(filter(lambda i: i['id'] == status3.id, response.data["statuses"]))["count"] == 1

    assert next(filter(lambda i: i['name'] == tag0, response.data["tags"]))["count"] == 0
    assert next(filter(lambda i: i['name'] == tag1, response.data["tags"]))["count"] == 2
    assert next(filter(lambda i: i['name'] == tag2, response.data["tags"]))["count"] == 2
    assert next(filter(lambda i: i['name'] == tag3, response.data["tags"]))["count"] == 1


def test_get_invalid_csv(client):
    url = reverse("userstories-csv")

    response = client.get(url)
    assert response.status_code == 404

    response = client.get("{}?uuid={}".format(url, "not-valid-uuid"))
    assert response.status_code == 404


def test_get_valid_csv(client):
    url = reverse("userstories-csv")
    project = f.ProjectFactory.create(userstories_csv_uuid=uuid.uuid4().hex)

    response = client.get("{}?uuid={}".format(url, project.userstories_csv_uuid))
    assert response.status_code == 200


def test_custom_fields_csv_generation():
    project = f.ProjectFactory.create(userstories_csv_uuid=uuid.uuid4().hex)
    attr = f.UserStoryCustomAttributeFactory.create(project=project, name="attr1", description="desc")
    us = f.UserStoryFactory.create(project=project)
    attr_values = us.custom_attributes_values
    attr_values.attributes_values = {str(attr.id): "val1"}
    attr_values.save()
    queryset = project.user_stories.all()
    data = services.userstories_to_csv(project, queryset)
    data.seek(0)
    reader = csv.reader(data)
    row = next(reader)
    assert row[28] == attr.name
    row = next(reader)
    assert row[28] == "val1"


def test_update_userstory_respecting_watchers(client):
    watching_user = f.create_user()
    project = f.ProjectFactory.create()
    us = f.UserStoryFactory.create(project=project, status__project=project, milestone__project=project)
    us.add_watcher(watching_user)
    f.MembershipFactory.create(project=us.project, user=us.owner, is_admin=True)
    f.MembershipFactory.create(project=us.project, user=watching_user)

    client.login(user=us.owner)
    url = reverse("userstories-detail", kwargs={"pk": us.pk})
    data = {"subject": "Updating test", "version": 1}

    response = client.json.patch(url, json.dumps(data))
    assert response.status_code == 200
    assert response.data["subject"] == "Updating test"
    assert response.data["watchers"] == [watching_user.id]


def test_update_userstory_update_watchers(client):
    watching_user = f.create_user()
    project = f.ProjectFactory.create()
    us = f.UserStoryFactory.create(project=project, status__project=project, milestone__project=project)
    f.MembershipFactory.create(project=us.project, user=us.owner, is_admin=True)
    f.MembershipFactory.create(project=us.project, user=watching_user)

    client.login(user=us.owner)
    url = reverse("userstories-detail", kwargs={"pk": us.pk})
    data = {"watchers": [watching_user.id], "version": 1}

    response = client.json.patch(url, json.dumps(data))
    assert response.status_code == 200
    assert response.data["watchers"] == [watching_user.id]
    watcher_ids = list(us.get_watchers().values_list("id", flat=True))
    assert watcher_ids == [watching_user.id]


def test_update_userstory_remove_watchers(client):
    watching_user = f.create_user()
    project = f.ProjectFactory.create()
    us = f.UserStoryFactory.create(project=project, status__project=project, milestone__project=project)
    us.add_watcher(watching_user)
    f.MembershipFactory.create(project=us.project, user=us.owner, is_admin=True)
    f.MembershipFactory.create(project=us.project, user=watching_user)

    client.login(user=us.owner)
    url = reverse("userstories-detail", kwargs={"pk": us.pk})
    data = {"watchers": [], "version": 1}

    response = client.json.patch(url, json.dumps(data))
    assert response.status_code == 200
    assert response.data["watchers"] == []
    watcher_ids = list(us.get_watchers().values_list("id", flat=True))
    assert watcher_ids == []


def test_update_userstory_update_tribe_gig(client):
    project = f.ProjectFactory.create()
    us = f.UserStoryFactory.create(project=project, status__project=project, milestone__project=project)
    f.MembershipFactory.create(project=us.project, user=us.owner, is_admin=True)

    url = reverse("userstories-detail", kwargs={"pk": us.pk})
    data = {
        "tribe_gig": {
            "id": 2,
            "title": "This is a gig test title"
        },
        "version": 1
    }

    client.login(user=us.owner)
    response = client.json.patch(url, json.dumps(data))

    assert response.status_code == 200
    assert response.data["tribe_gig"] == data["tribe_gig"]


def test_get_user_stories_including_tasks(client):
    user = f.UserFactory.create()
    project = f.ProjectFactory.create(owner=user)
    f.MembershipFactory.create(project=project, user=user, is_admin=True)

    user_story = f.UserStoryFactory.create(project=project)
    f.TaskFactory.create(user_story=user_story)
    url = reverse("userstories-list")

    client.login(project.owner)

    response = client.get(url)
    assert response.status_code == 200
    assert response.data[0].get("tasks") == []

    url = reverse("userstories-list") + "?include_tasks=1"
    response = client.get(url)
    assert response.status_code == 200
    assert len(response.data[0].get("tasks")) == 1


def test_get_user_stories_including_attachments(client):
    user = f.UserFactory.create()
    project = f.ProjectFactory.create(owner=user)
    f.MembershipFactory.create(project=project, user=user, is_admin=True)

    user_story = f.UserStoryFactory.create(project=project)
    f.UserStoryAttachmentFactory(project=project, content_object=user_story)
    url = reverse("userstories-list")

    client.login(project.owner)

    response = client.get(url)
    assert response.status_code == 200
    assert response.data[0].get("attachments") == []

    url = reverse("userstories-list") + "?include_attachments=1"
    response = client.get(url)
    assert response.status_code == 200
    assert len(response.data[0].get("attachments")) == 1
