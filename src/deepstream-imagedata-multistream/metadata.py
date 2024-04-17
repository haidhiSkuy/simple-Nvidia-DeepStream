import pyds
import sys
sys.path.append('../')

pgie_class_id_vehicle = 0
pgie_class_id_person = 2
max_time_stamp_len = 32

def generate_vehicle_meta(data):
    obj = pyds.NvDsVehicleObject.cast(data)
    obj.type = "sedan"
    obj.color = "blue"
    obj.make = "Bugatti"
    obj.model = "M"
    obj.license = "XX1234"
    obj.region = "CA"
    return obj

def generate_person_meta(data):
    obj = pyds.NvDsPersonObject.cast(data)
    obj.age = 45
    obj.cap = "none"
    obj.hair = "black"
    obj.gender = "male"
    obj.apparel = "formal"
    return obj

def generate_event_msg_meta(data, class_id):
    meta = pyds.NvDsEventMsgMeta.cast(data)
    meta.sensorId = 0
    meta.placeId = 0
    meta.moduleId = 0
    meta.sensorStr = "sensor-0"
    meta.ts = pyds.alloc_buffer(max_time_stamp_len + 1)
    pyds.generate_ts_rfc3339(meta.ts, max_time_stamp_len)

    # if class_id == pgie_class_id_vehicle:
    #     meta.type = pyds.NvDsEventType.NVDS_EVENT_MOVING
    #     meta.objType = pyds.NvDsObjectType.NVDS_OBJECT_TYPE_VEHICLE
    #     meta.objClassId = pgie_class_id_vehicle
    #     obj = pyds.alloc_nvds_vehicle_object()
    #     obj = generate_vehicle_meta(obj)
    #     meta.extMsg = obj
    #     meta.extMsgSize = sys.getsizeof(pyds.NvDsVehicleObject)

    # if class_id == pgie_class_id_person:
    #     meta.type = pyds.NvDsEventType.NVDS_EVENT_ENTRY
    #     meta.objType = pyds.NvDsObjectType.NVDS_OBJECT_TYPE_PERSON
    #     meta.objClassId = pgie_class_id_person
    #     obj = pyds.alloc_nvds_person_object()
    #     obj = generate_person_meta(obj)
    #     meta.extMsg = obj
    #     meta.extMsgSize = sys.getsizeof(pyds.NvDsPersonObject)
    return meta